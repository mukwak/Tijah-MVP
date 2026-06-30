"""Voice processing: Speech-to-Text (Whisper) and Text-to-Speech (edge-tts)."""
import logging
import tempfile
import os
import hashlib
import edge_tts
from openai import AsyncOpenAI
from app.config import OPENAI_API_KEY, AUDIO_CACHE_DIR

log = logging.getLogger("tijah")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Nigerian-friendly voice options
VOICES = {
    "en": "en-NG-AbeoNeural",       # Nigerian English male
    "en_f": "en-NG-EzinneNeural",    # Nigerian English female
    "pidgin": "en-NG-AbeoNeural",    # Use Nigerian English voice for Pidgin too
}


async def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio using OpenAI Whisper. Handles Nigerian English and Pidgin."""
    suffix = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        f.flush()
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcript = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",  # Works well for Nigerian English & Pidgin
                prompt="Nigerian Pidgin English. Shop sales, stock, credit, customer names. "
                       "Naira currency. Examples: I sell, I buy, e owe me, how much, "
                       "wetin I sell today, how my shop do",
            )
        return transcript.text.strip()
    finally:
        os.unlink(tmp_path)


async def text_to_speech(text: str, language: str = "pidgin") -> str:
    """Convert text to speech using edge-tts (free). Returns path to mp3 file."""
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

    # Cache by text hash to avoid regenerating
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    output_path = os.path.join(AUDIO_CACHE_DIR, f"{text_hash}.mp3")

    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        log.info(f"TTS cache hit: {output_path} ({file_size} bytes)")
        if file_size > 0:
            return output_path
        # Cached file is empty/corrupt — regenerate
        os.remove(output_path)

    voice = VOICES.get(language, VOICES["pidgin"])
    log.info(f"TTS generating: voice={voice}, text_len={len(text)}")

    # Truncate very long text to avoid edge-tts timeouts
    tts_text = text[:500] if len(text) > 500 else text

    communicate = edge_tts.Communicate(
        text=tts_text,
        voice=voice,
        rate="-10%",  # Slightly slower for clarity
    )
    await communicate.save(output_path)

    file_size = os.path.getsize(output_path)
    log.info(f"TTS saved: {output_path} ({file_size} bytes)")
    if file_size == 0:
        os.remove(output_path)
        raise RuntimeError("edge-tts produced empty audio file")

    return output_path
