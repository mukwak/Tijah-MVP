"""Tijah MVP - Voice-First WhatsApp Shop Manager for Nigerian Traders.

Main FastAPI application with WhatsApp webhook handler.
"""
import logging
import os
import traceback
import hashlib
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, HTMLResponse

from app.config import WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN, VERIFY_WEBHOOK_SIGNATURE
from app.database import get_db, close_db, try_mark_message_processed
from app.whatsapp import send_text, send_audio, download_media, send_interactive_buttons
from app.voice import transcribe, text_to_speech
from app.nlu import parse_intent
from app.preclassifier import preclassify
from app.responses import get_response
from app.config import ADMIN_TOKEN
from app.report import (
    get_phone_by_token, render_report_html, render_admin_html,
    get_customer_by_receipt_token, render_customer_receipt_html,
)
from app import handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tijah")


def _fmt(num) -> str:
    """Format number with commas for nudge messages."""
    num = float(num)
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Tijah starting up...")
    await get_db()
    log.info("Database ready")
    yield
    await close_db()
    log.info("Tijah shut down")


app = FastAPI(title="Tijah", description="Voice-first WhatsApp shop manager", lifespan=lifespan)


@app.get("/webhook")
async def verify_webhook(request: Request):
    """WhatsApp webhook verification (GET request from Meta)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        log.info("Webhook verified")
        return PlainTextResponse(content=challenge)

    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook")
async def handle_webhook(request: Request):
    """Handle incoming WhatsApp messages."""
    raw_body = await request.body()
    if not _verify_webhook_signature(request, raw_body):
        log.warning("Rejected webhook with invalid or missing Meta signature")
        return PlainTextResponse(content="Forbidden", status_code=403)

    body = await request.json()

    try:
        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                for message in messages:
                    try:
                        await _process_message(message)
                    except Exception as e:
                        log.error(f"Message processing error: {e}\n{traceback.format_exc()}")
                        # Guaranteed error response — never leave user hanging
                        phone = message.get("from", "")
                        if phone:
                            try:
                                await send_text(phone, get_response("error", "english"))
                            except Exception:
                                log.error("Failed to send error response")
    except Exception as e:
        log.error(f"Webhook error: {e}\n{traceback.format_exc()}")

    # Always return 200 to WhatsApp
    return Response(status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tijah"}


@app.get("/admin/{token}")
async def admin_dashboard(token: str):
    """Admin overview, protected by ADMIN_TOKEN env var."""
    if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
        return HTMLResponse(content="<h3>Not found</h3>", status_code=404)
    return HTMLResponse(content=await render_admin_html())


@app.get("/report/{token}")
async def shop_report(token: str):
    """Shareable read-only report page for a shop, keyed by unguessable token."""
    phone = await get_phone_by_token(token)
    if not phone:
        return HTMLResponse(content="<h3>Report not found</h3>", status_code=404)
    return HTMLResponse(content=await render_report_html(phone))


@app.get("/receipt/{token}")
async def customer_receipt(token: str):
    """Per-customer receipt page — safe to share with the customer."""
    result = await get_customer_by_receipt_token(token)
    if not result:
        return HTMLResponse(content="<h3>Receipt not found</h3>", status_code=404)
    phone, customer = result
    return HTMLResponse(content=await render_customer_receipt_html(phone, customer))


@app.get("/cron/daily-nudge")
async def daily_nudge(request: Request):
    """Send evening summary to active users. Call from external cron service."""
    token = request.query_params.get("token", "")
    if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
        return PlainTextResponse("Forbidden", status_code=403)

    db = await get_db()

    # Find shops active in the last 7 days
    cursor = await db.execute(
        """SELECT DISTINCT s.phone, s.language FROM shops s
           WHERE EXISTS (
               SELECT 1 FROM sales WHERE sales.phone = s.phone
               AND sales.created_at >= datetime('now', '+1 hours', '-7 days')
           )"""
    )
    active_shops = await cursor.fetchall()

    sent = 0
    for shop in active_shops:
        phone, lang = shop[0], shop[1] or "english"

        cursor = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND date(created_at) = date('now', '+1 hours')",
            (phone,),
        )
        row = await cursor.fetchone()
        sales_count, sales_total = row[0], row[1]

        if sales_count > 0:
            msg = get_response("nudge_evening_active", lang,
                               sales_count=sales_count, sales_total=_fmt(sales_total))
        else:
            msg = get_response("nudge_evening_idle", lang)

        try:
            await send_text(phone, msg)
            sent += 1
        except Exception as e:
            log.error(f"Nudge failed for {phone}: {e}")

    return {"sent": sent, "total_active": len(active_shops)}


@app.get("/cron/morning-nudge")
async def morning_nudge(request: Request):
    """Send a morning reminder to active users. Call from external cron at ~8am WAT."""
    token = request.query_params.get("token", "")
    if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
        return PlainTextResponse("Forbidden", status_code=403)

    db = await get_db()

    # Find shops active in the last 7 days
    cursor = await db.execute(
        """SELECT DISTINCT s.phone, s.language FROM shops s
           WHERE EXISTS (
               SELECT 1 FROM sales WHERE sales.phone = s.phone
               AND sales.created_at >= datetime('now', '+1 hours', '-7 days')
           )"""
    )
    active_shops = await cursor.fetchall()

    sent = 0
    for shop in active_shops:
        phone, lang = shop[0], shop[1] or "english"
        msg = get_response("nudge_morning", lang)
        try:
            await send_text(phone, msg)
            sent += 1
        except Exception as e:
            log.error(f"Morning nudge failed for {phone}: {e}")

    return {"sent": sent, "total_active": len(active_shops)}


async def _process_message(message: dict):
    """Process a single incoming WhatsApp message."""
    msg_id = message.get("id", "")

    # Persistently deduplicate WhatsApp retries and worker restarts.
    if not await try_mark_message_processed(msg_id):
        return

    phone = message.get("from", "")
    msg_type = message.get("type", "")

    log.info(f"Message from {phone}: type={msg_type}")

    db = await get_db()

    # Get or create shop
    cursor = await db.execute("SELECT language, onboarded, name FROM shops WHERE phone = ?", (phone,))
    shop = await cursor.fetchone()

    is_new_user = shop is None
    if is_new_user:
        # New user — create shop but DON'T send welcome yet.
        # Process their message first (helpfulness trumps onboarding).
        await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (phone,))
        await db.commit()
        lang = "english"
    else:
        lang = shop[0] or "english"

    is_voice = msg_type == "audio"

    # Handle button replies directly (no NLU needed)
    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            button_id = interactive.get("button_reply", {}).get("id", "")
            if button_id in ("confirm_yes", "confirm_no"):
                intent = {"action": button_id}
                response_text = await _route_intent(phone, intent, lang)
                await _send_response(phone, response_text, lang)
                return

    # Extract text from message
    text = await _extract_text(message, msg_type)

    if not text:
        await send_text(phone, get_response("not_understood", lang))
        return

    log.info(f"User text: {text}")

    # Fast pre-classifier — skip Gemini for simple intents
    intent = preclassify(text)
    if intent:
        log.info(f"Pre-classified: {intent}")
    else:
        # Full NLU parse via Gemini
        intent = await parse_intent(text, lang)
        log.info(f"Intent: {intent}")

    # Use detected language from NLU, fall back to stored preference
    lang = intent.pop("detected_language", lang)

    # Tag voice messages so handlers can offer name verification
    if is_voice:
        intent["_is_voice"] = True

    # Route to handler
    response_text = await _route_intent(phone, intent, lang)

    # Onboarding: fold welcome into the first response (one message, not two)
    if is_new_user:
        action = intent.get("action", "help")
        if action in ("greeting", "help"):
            # They said hi — the welcome IS the response (replaces generic greeting)
            response_text = get_response("welcome", lang)
        else:
            # They jumped straight to business — be helpful first, then introduce
            response_text += get_response("welcome_after_action", lang)

    # If response is a confirmation prompt, send as interactive buttons
    if any(phrase in response_text for phrase in [
        'Say "yes"', 'Say "no"', "same person", "na the same person"
    ]):
        yes_label = "Yes, same person" if lang == "english" else "Yes, na dem"
        no_label = "No, new person" if lang == "english" else "No, another person"
        await send_interactive_buttons(phone, response_text, [
            {"id": "confirm_yes", "title": yes_label[:20]},
            {"id": "confirm_no", "title": no_label[:20]},
        ])
        return

    # For voice messages, echo back what we heard so user can verify
    if is_voice:
        echo = get_response("voice_echo", lang, text=text)
        response_text = echo + response_text

    # Send response - voice reply only if user sent a voice note
    await _send_response(phone, response_text, lang, include_voice=is_voice)


async def _extract_text(message: dict, msg_type: str) -> str | None:
    """Extract text from message - handle voice, text, and button replies."""
    if msg_type == "text":
        return message.get("text", {}).get("body", "")

    elif msg_type == "audio":
        # Voice message - transcribe with Whisper
        audio_info = message.get("audio", {})
        media_id = audio_info.get("id")
        if media_id:
            try:
                audio_bytes = await download_media(media_id)
                text = await transcribe(audio_bytes)
                log.info(f"Transcribed: {text}")
                return text
            except Exception as e:
                log.error(f"Transcription error: {e}")
                return None

    elif msg_type == "interactive":
        # Button reply
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            return interactive.get("button_reply", {}).get("title", "")

    return None


async def _route_intent(phone: str, intent: dict, lang: str) -> str:
    """Route parsed intent to the appropriate handler."""
    action = intent.get("action", "help")

    handler_map = {
        "record_sale": handlers.handle_record_sale,
        "add_stock": handlers.handle_add_stock,
        "record_credit": handlers.handle_record_credit,
        "record_payment": handlers.handle_record_payment,
        "check_stock": handlers.handle_check_stock,
        "check_credits": handlers.handle_check_credits,
        "daily_summary": handlers.handle_daily_summary,
        "record_expense": handlers.handle_record_expense,
        "check_expenses": handlers.handle_check_expenses,
        "set_price": handlers.handle_set_price,
        "change_language": handlers.handle_change_language,
        "check_sales": handlers.handle_check_sales,
        "credit_history": handlers.handle_credit_history,
        "edit_credit": handlers.handle_edit_credit,
        "credit_reminder": handlers.handle_credit_reminder,
        "edit_last": handlers.handle_edit_last,
        "undo": handlers.handle_undo,
        "multi_sale": handlers.handle_multi_sale,
        "confirm_yes": handlers.handle_confirm_yes,
        "confirm_no": handlers.handle_confirm_no,
        "rename_customer": handlers.handle_rename_customer,
        "get_report": handlers.handle_get_report,
        "feedback": handlers.handle_feedback,
        "set_shop_name": handlers.handle_set_shop_name,
        "customer_statement": handlers.handle_customer_statement,
    }

    handler = handler_map.get(action)

    if handler:
        try:
            return await handler(phone, intent, lang)
        except Exception as e:
            log.error(f"Handler error [{action}]: {e}\n{traceback.format_exc()}")
            return get_response("error", lang)

    if action == "greeting":
        return get_response("greeting", lang)

    if action == "help":
        return get_response("help", lang)

    return get_response("not_understood", lang)


async def _send_response(phone: str, text: str, lang: str, include_voice: bool = False):
    """Send response - always text, voice note only if user sent a voice message."""
    log.info(f"Sending response to {phone}: include_voice={include_voice}, text_len={len(text)}")
    await send_text(phone, text)

    if include_voice:
        try:
            log.info(f"Generating TTS for voice reply to {phone}")
            audio_path = await text_to_speech(text, lang)
            log.info(f"TTS generated: {audio_path}, sending audio...")
            await send_audio(phone, audio_path)
            log.info("Voice reply sent successfully")
        except Exception as e:
            log.error(f"TTS/audio send failed: {e}", exc_info=True)


def _verify_webhook_signature(request: Request, raw_body: bytes) -> bool:
    """Verify Meta's X-Hub-Signature-256 header."""
    if not VERIFY_WEBHOOK_SIGNATURE:
        return True
    if not WHATSAPP_APP_SECRET:
        log.error("VERIFY_WEBHOOK_SIGNATURE=true but META_APP_SECRET is not configured")
        return False

    signature = request.headers.get("x-hub-signature-256", "")
    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")
