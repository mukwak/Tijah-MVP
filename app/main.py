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


@app.get("/privacy")
async def privacy_page():
    """Plain-language privacy policy page."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tijah - Privacy</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; font-size: 16px; line-height: 1.6;
         max-width: 600px; margin: 0 auto; padding: 20px; color: #333; }
  h1 { font-size: 1.4rem; margin-bottom: 10px; }
  h2 { font-size: 1.1rem; margin: 20px 0 8px; color: #1a73e8; }
  p, li { margin-bottom: 8px; }
  ul { padding-left: 20px; }
  .lang-toggle { text-align: center; margin: 15px 0; }
  .lang-toggle button { padding: 8px 16px; margin: 0 5px; border: 1px solid #ccc;
    border-radius: 6px; background: #f5f5f5; cursor: pointer; font-size: 0.9rem; }
  .lang-toggle button.active { background: #1a73e8; color: white; border-color: #1a73e8; }
  .section { display: none; }
  .section.active { display: block; }
  footer { text-align: center; color: #999; font-size: 0.75rem; padding: 30px 0 10px; }
</style>
</head>
<body>
<h1>Tijah Privacy Policy</h1>
<div class="lang-toggle">
  <button class="active" onclick="show('en',this)">English</button>
  <button onclick="show('pid',this)">Pidgin</button>
</div>

<div id="en" class="section active">
<h2>What we save</h2>
<ul>
  <li>Your phone number (so we know it's your shop)</li>
  <li>Sales, stock, and expense records you tell us</li>
  <li>Customer names and credit/payment amounts</li>
  <li>What you say in voice notes (we turn it to text, we don't keep the audio)</li>
</ul>

<h2>Why we save it</h2>
<p>To help you track your shop — sales, stock, who owes you, expenses, and profit.</p>

<h2>Who can see your data</h2>
<ul>
  <li><strong>Only you</strong> — through your phone or your report link</li>
  <li>Customer receipt links only show that one customer's record</li>
  <li>We do NOT sell, share, or give your data to anyone</li>
</ul>

<h2>How we protect it</h2>
<p>Your data is stored securely. Report and receipt links use private tokens that cannot be guessed.</p>

<h2>How to delete your data</h2>
<p>Send Tijah the message <strong>"delete my data"</strong> at any time. All your records will be permanently removed. This cannot be undone.</p>

<h2>Your consent</h2>
<p>By sending messages to Tijah, you agree that we can save your shop records to help you track your business. You can withdraw consent at any time by deleting your data.</p>

<h2>Contact</h2>
<p>If you have questions, send Tijah the message "I have a complaint" or "feedback".</p>
</div>

<div id="pid" class="section">
<h2>Wetin we save</h2>
<ul>
  <li>Your phone number (so we go know say na your shop)</li>
  <li>Sales, stock, and expense record wey you tell us</li>
  <li>Customer name and how much dem owe or pay</li>
  <li>Wetin you talk for voice note (we change am to text, we no keep the audio)</li>
</ul>

<h2>Why we save am</h2>
<p>To help you track your shop — sales, stock, who owe you, expenses, and profit.</p>

<h2>Who fit see your data</h2>
<ul>
  <li><strong>Only you</strong> — through your phone or your report link</li>
  <li>Customer receipt link only show that one customer own record</li>
  <li>We no dey sell, share, or give your data to anybody</li>
</ul>

<h2>How we protect am</h2>
<p>Your data dey safe for secure server. Report and receipt link get private code wey nobody fit guess.</p>

<h2>How to delete your data</h2>
<p>Send Tijah <strong>"delete my data"</strong> anytime. All your record go disappear permanently. E no fit reverse.</p>

<h2>Your consent</h2>
<p>When you send message to Tijah, you agree say we fit save your shop record to help you. You fit remove your consent anytime — just delete your data.</p>

<h2>Contact</h2>
<p>If you get question, send Tijah "I get complaint" or "feedback".</p>
</div>

<footer>Tijah &copy; 2026</footer>
<script>
function show(id, btn) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.lang-toggle button').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


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
        """SELECT DISTINCT s.phone, s.language, s.voice_user FROM shops s
           WHERE EXISTS (
               SELECT 1 FROM sales WHERE sales.phone = s.phone
               AND sales.created_at >= datetime('now', '+1 hours', '-7 days')
           )"""
    )
    active_shops = await cursor.fetchall()

    sent = 0
    for shop in active_shops:
        phone, lang, is_voice_user = shop[0], shop[1] or "english", shop[2] or 0

        cursor = await db.execute(
            "SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND date(created_at) = date('now', '+1 hours')",
            (phone,),
        )
        row = await cursor.fetchone()
        sales_count, sales_total = int(row[0]), row[1]

        if sales_count > 0:
            msg = get_response("nudge_evening_active", lang,
                               sales_count=sales_count, sales_total=_fmt(sales_total))
        else:
            msg = get_response("nudge_evening_idle", lang)

        # Debt aging: mention oldest unpaid debt (>14 days)
        cursor = await db.execute(
            """SELECT customer, amount, created_at FROM credits
               WHERE phone = ? AND settled = 0
               AND created_at <= datetime('now', '+1 hours', '-14 days')
               ORDER BY created_at ASC LIMIT 1""",
            (phone,),
        )
        old_debt = await cursor.fetchone()
        if old_debt:
            customer, amount, created_at = old_debt[0], old_debt[1], old_debt[2]
            days_ago = (await (await db.execute(
                "SELECT CAST(julianday('now', '+1 hours') - julianday(?) AS INTEGER)",
                (created_at,),
            )).fetchone())[0]
            msg += get_response("nudge_debt_aging", lang,
                                customer=customer, amount=_fmt(amount), days=days_ago)

        # Top seller insight
        if sales_count > 0:
            cursor = await db.execute(
                """SELECT p.name, SUM(sa.total) as rev FROM sales sa
                   JOIN products p ON sa.product_id = p.id
                   WHERE sa.phone = ? AND date(sa.created_at) = date('now', '+1 hours')
                   GROUP BY p.name ORDER BY rev DESC LIMIT 1""",
                (phone,),
            )
            top = await cursor.fetchone()
            if top and top[0] != "(general sales)":
                msg += get_response("nudge_top_seller", lang,
                                    product=top[0], total=_fmt(top[1]))

        # Low stock alert: products with stock tracked and quantity <= 5
        cursor = await db.execute(
            """SELECT name, stock_qty, unit FROM products
               WHERE phone = ? AND stock_qty > 0 AND stock_qty <= 5
               ORDER BY stock_qty ASC LIMIT 2""",
            (phone,),
        )
        low_stock = await cursor.fetchall()
        if low_stock:
            items = ", ".join(f"{row[0]} ({_fmt(row[1])} {row[2] or 'left'})" for row in low_stock)
            msg += get_response("nudge_low_stock", lang, items=items)

        try:
            await send_text(phone, msg)
            if is_voice_user:
                try:
                    audio_path = await text_to_speech(msg, lang)
                    await send_audio(phone, audio_path)
                except Exception as e:
                    log.error(f"Nudge TTS failed for {phone}: {e}")
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
        """SELECT DISTINCT s.phone, s.language, s.voice_user FROM shops s
           WHERE EXISTS (
               SELECT 1 FROM sales WHERE sales.phone = s.phone
               AND sales.created_at >= datetime('now', '+1 hours', '-7 days')
           )"""
    )
    active_shops = await cursor.fetchall()

    sent = 0
    for shop in active_shops:
        phone, lang, is_voice_user = shop[0], shop[1] or "english", shop[2] or 0
        msg = get_response("nudge_morning", lang)
        try:
            await send_text(phone, msg)
            if is_voice_user:
                try:
                    audio_path = await text_to_speech(msg, lang)
                    await send_audio(phone, audio_path)
                except Exception as e:
                    log.error(f"Morning nudge TTS failed for {phone}: {e}")
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

    # Mark user as voice-preferring so nudges can include TTS
    if is_voice and not is_new_user:
        await db.execute("UPDATE shops SET voice_user = 1 WHERE phone = ? AND voice_user = 0", (phone,))
        await db.commit()

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

    # Very long voice note (>45s): echo transcription and ask user to confirm
    # before processing — Whisper may have lost content at the tail end
    if message.get("_very_long_voice"):
        from app.handlers import _save_pending
        await _save_pending(db, phone, {
            "action": "long_voice_confirm",
            "text": text,
            "lang": lang,
        })
        echo = get_response("voice_echo", lang, text=text)
        confirm_msg = get_response("long_voice_confirm", lang)
        await send_text(phone, echo + confirm_msg)
        return

    # Fast pre-classifier — skip Gemini for simple intents
    intent = preclassify(text)
    if intent:
        log.info(f"Pre-classified: {intent}")
    else:
        # Full NLU parse via Gemini
        intent = await parse_intent(text, lang)
        log.info(f"Intent: {intent}")
        # If NLU failed to parse, ask for clarification instead of silent fallback
        if intent.get("error") and intent.get("action") == "help":
            log.warning(f"NLU parse failed: {intent['error']}")
            intent = {"action": "_clarify"}

    # Use detected language from NLU, fall back to stored preference
    lang = intent.pop("detected_language", lang)

    # Tag voice messages so handlers can offer name verification
    if is_voice:
        intent["_is_voice"] = True

    # Clear stale pending actions when user sends a new business message
    # (not confirm_yes/no — those need the pending action)
    action = intent.get("action", "")
    if action not in ("confirm_yes", "confirm_no", "_clarify", ""):
        from app.handlers import _clear_pending
        await _clear_pending(db, phone)

    # Route to handler
    response_text = await _route_intent(phone, intent, lang)

    # Long voice replay: confirm_yes returned saved text to re-process through NLU
    if response_text.startswith("__replay__:"):
        replay_text = response_text[len("__replay__:"):]
        log.info(f"Replaying confirmed long voice text: {replay_text[:80]}...")
        replay_intent = preclassify(replay_text)
        if not replay_intent:
            replay_intent = await parse_intent(replay_text, lang)
            if replay_intent.get("error") and replay_intent.get("action") == "help":
                replay_intent = {"action": "_clarify"}
        lang = replay_intent.pop("detected_language", lang)
        replay_intent["_is_voice"] = True
        response_text = await _route_intent(phone, replay_intent, lang)

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
        # Determine button labels based on context
        if "total" in response_text and "each" in response_text and ("cash" not in response_text.lower()):
            # Price clarification
            yes_label = "Total" if lang == "english" else "Na total"
            no_label = "Each" if lang == "english" else "Na each"
        elif "cash" in response_text.lower() and "credit" in response_text.lower():
            # Credit clarification
            yes_label = "Cash" if lang == "english" else "Na cash"
            no_label = "Credit" if lang == "english" else "Na credit"
        else:
            # Customer name confirmation
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
        # Long voice note: one-time hint to send shorter messages (Option 3)
        if message.get("_long_voice"):
            cursor = await db.execute(
                "SELECT long_voice_hinted FROM shops WHERE phone = ?", (phone,))
            hint_row = await cursor.fetchone()
            if hint_row and not hint_row[0]:
                response_text += get_response("hint_long_voice", lang)
                await db.execute(
                    "UPDATE shops SET long_voice_hinted = 1 WHERE phone = ?", (phone,))
                await db.commit()

    # For new voice users, prepend a spoken intro so they hear who Tijah is
    if is_new_user and is_voice:
        tip = get_response("welcome_voice_tip", lang)
        response_text = tip + response_text

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
                log.info(f"Transcribed: {text} (audio_size={len(audio_bytes)})")
                # Flag long voice notes so _process_message can warn user
                # WhatsApp opus ~1-2KB/sec, 40KB ~ 30s+, 60KB ~ 45s+
                if len(audio_bytes) > 40_000:
                    message["_long_voice"] = True
                # Very long voice note (>45s): flag for echo-and-confirm
                if len(audio_bytes) > 60_000:
                    message["_very_long_voice"] = True
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
        "payment_and_credit": handlers.handle_payment_and_credit,
        "check_stock": handlers.handle_check_stock,
        "check_credits": handlers.handle_check_credits,
        "daily_summary": handlers.handle_daily_summary,
        "record_expense": handlers.handle_record_expense,
        "multi_expense": handlers.handle_multi_expense,
        "check_expenses": handlers.handle_check_expenses,
        "set_price": handlers.handle_set_price,
        "change_language": handlers.handle_change_language,
        "check_sales": handlers.handle_check_sales,
        "credit_history": handlers.handle_credit_history,
        "edit_credit": handlers.handle_edit_credit,
        "credit_reminder": handlers.handle_credit_reminder,
        "edit_last": handlers.handle_edit_last,
        "mark_credit": handlers.handle_mark_credit,
        "undo": handlers.handle_undo,
        "multi_sale": handlers.handle_multi_sale,
        "confirm_yes": handlers.handle_confirm_yes,
        "confirm_no": handlers.handle_confirm_no,
        "rename_customer": handlers.handle_rename_customer,
        "get_report": handlers.handle_get_report,
        "feedback": handlers.handle_feedback,
        "set_shop_name": handlers.handle_set_shop_name,
        "customer_statement": handlers.handle_customer_statement,
        "check_payments": handlers.handle_check_payments,
        "merge_products": handlers.handle_merge_products,
        "what_can_you_do": handlers.handle_what_can_you_do,
        "record_bulk_sale": handlers.handle_record_bulk_sale,
        "privacy": handlers.handle_privacy,
        "delete_data": handlers.handle_delete_data,
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

    if action == "_clarify":
        return get_response("clarify", lang)

    return get_response("not_understood", lang)


async def _send_response(phone: str, text: str, lang: str, include_voice: bool = False):
    """Send response - always text, voice note only if user sent a voice message."""
    log.info(f"Sending response to {phone}: include_voice={include_voice}, text_len={len(text)}")
    await send_text(phone, text)

    if include_voice:
        try:
            log.info(f"Generating TTS for voice reply to {phone}")
            result = await text_to_speech(text, lang)
            if isinstance(result, list):
                # Multiple audio chunks for long responses
                log.info(f"TTS generated {len(result)} chunks, sending sequentially...")
                for audio_path in result:
                    await send_audio(phone, audio_path)
            else:
                log.info(f"TTS generated: {result}, sending audio...")
                await send_audio(phone, result)
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
