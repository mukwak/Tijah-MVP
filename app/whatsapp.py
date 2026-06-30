"""WhatsApp Business Cloud API client."""
import logging
import httpx
import os
import tempfile
from app.config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID

log = logging.getLogger("tijah")

API_BASE = "https://graph.facebook.com/v21.0"


async def send_text(to: str, text: str):
    """Send a text message."""
    url = f"{API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def send_audio(to: str, audio_path: str):
    """Upload and send an audio message."""
    file_size = os.path.getsize(audio_path)
    log.info(f"send_audio: uploading {audio_path} ({file_size} bytes)")

    # First upload the media
    url = f"{API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=60) as client:
        with open(audio_path, "rb") as f:
            files = {"file": ("response.mp3", f, "audio/mpeg")}
            data = {"messaging_product": "whatsapp", "type": "audio/mpeg"}
            resp = await client.post(url, headers=headers, files=files, data=data)
            log.info(f"send_audio: upload response {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            media_id = resp.json()["id"]

        # Send the audio message
        log.info(f"send_audio: sending media_id={media_id} to {to}")
        msg_url = f"{API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id},
        }
        resp = await client.post(msg_url, json=payload, headers=headers)
        log.info(f"send_audio: send response {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()


async def download_media(media_id: str) -> bytes:
    """Download media file from WhatsApp."""
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        # Get media URL
        url = f"{API_BASE}/{media_id}"
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        media_url = resp.json()["url"]

        # Download the actual file
        resp = await client.get(media_url, headers=headers)
        resp.raise_for_status()
        return resp.content


async def send_interactive_buttons(to: str, body: str, buttons: list[dict]):
    """Send interactive button message. buttons: [{"id": "x", "title": "X"}, ...]"""
    url = f"{API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]  # WhatsApp max 3 buttons
                ]
            },
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
