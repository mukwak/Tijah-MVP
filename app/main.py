"""Tijah MVP - Voice-First WhatsApp Shop Manager for Nigerian Traders.

Main FastAPI application with WhatsApp webhook handler.
"""
import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import WHATSAPP_VERIFY_TOKEN
from app.database import get_db, close_db
from app.whatsapp import send_text, send_audio, download_media, send_interactive_buttons
from app.voice import transcribe, text_to_speech
from app.nlu import parse_intent
from app.responses import get_response
from app import handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tijah")

# Track processed message IDs to avoid duplicates
_processed_messages = set()
MAX_PROCESSED_CACHE = 10000


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
    body = await request.json()

    try:
        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                for message in messages:
                    await _process_message(message)
    except Exception as e:
        log.error(f"Webhook error: {e}\n{traceback.format_exc()}")

    # Always return 200 to WhatsApp
    return Response(status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tijah"}


async def _process_message(message: dict):
    """Process a single incoming WhatsApp message."""
    msg_id = message.get("id", "")

    # Deduplicate
    if msg_id in _processed_messages:
        return
    _processed_messages.add(msg_id)
    if len(_processed_messages) > MAX_PROCESSED_CACHE:
        # Remove oldest entries (set doesn't preserve order, but this prevents unbounded growth)
        _processed_messages.clear()

    phone = message.get("from", "")
    msg_type = message.get("type", "")

    log.info(f"Message from {phone}: type={msg_type}")

    db = await get_db()

    # Get or create shop
    cursor = await db.execute("SELECT language, onboarded, name FROM shops WHERE phone = ?", (phone,))
    shop = await cursor.fetchone()

    if not shop:
        # New user - create shop, send welcome, and process their message
        await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (phone, 1))
        await db.commit()
        is_voice = msg_type == "audio"
        await _send_response(phone, get_response("welcome", "english"), "english", include_voice=is_voice)
        return

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

    # Always parse intent first — listen to what the user is saying
    intent = await parse_intent(text, lang)
    log.info(f"Intent: {intent}")

    # Use detected language from NLU, fall back to stored preference
    lang = intent.pop("detected_language", lang)

    # Route to handler
    response_text = await _route_intent(phone, intent, lang)

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
