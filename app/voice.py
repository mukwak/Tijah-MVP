"""Voice processing: Speech-to-Text (Whisper) and Text-to-Speech (OpenAI TTS)."""
import logging
import re
import tempfile
import os
import hashlib
from openai import AsyncOpenAI
from app.config import OPENAI_API_KEY, AUDIO_CACHE_DIR

log = logging.getLogger("tijah")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


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


def _make_speakable(text: str) -> str:
    """Convert formatted text into natural conversational speech."""
    s = text

    # Strip the "I heard: ..." echo — don't repeat what user said back in voice
    s = re.sub(r'I hear(?:d)?(?: you say)?:?\s*"[^"]*"\s*', '', s)

    # "Sold! 3 bag rice = 60,000 naira" → "Done! 3 bag rice, 60 thousand naira"
    s = s.replace(" = ", ", ")
    s = s.replace("Sold!", "Done!")
    s = s.replace("Stocked!", "Got it!")

    # Remove list indentation and bullet formatting
    s = re.sub(r'\n\s{2,}', '\n', s)

    # Convert formatted numbers: "60,000" → "60 thousand", "1,500,000" → "1.5 million"
    def _speak_number(m: re.Match) -> str:
        raw = m.group(0).replace(",", "")
        n = float(raw)
        if n >= 1_000_000:
            val = n / 1_000_000
            return f"{val:g} million"
        if n >= 1_000:
            val = n / 1_000
            return f"{val:g} thousand"
        return raw

    s = re.sub(r'\d{1,3}(?:,\d{3})+', _speak_number, s)

    # "naira" after number is fine, but clean up double spaces
    s = re.sub(r'  +', ' ', s)

    # Replace newlines with pauses (periods/commas)
    s = re.sub(r'\n{2,}', '. ', s)
    s = re.sub(r'\n', ', ', s)

    # Clean up awkward punctuation from replacements
    s = re.sub(r':\s*,', ':', s)  # "owing you:, " → "owing you: "
    s = re.sub(r'[.,]\s*[.,]', '.', s)
    s = re.sub(r'\s+\.', '.', s)

    return s.strip()


async def text_to_speech(text: str, language: str = "pidgin") -> str:
    """Convert text to speech using OpenAI TTS. Returns path to mp3 file."""
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

    # Convert to conversational speech
    speech_text = _make_speakable(text)

    # Cache by text hash to avoid regenerating
    text_hash = hashlib.md5(speech_text.encode()).hexdigest()[:12]
    output_path = os.path.join(AUDIO_CACHE_DIR, f"{text_hash}.mp3")

    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        log.info(f"TTS cache hit: {output_path} ({file_size} bytes)")
        if file_size > 0:
            return output_path
        os.remove(output_path)

    # Truncate very long text to keep costs down
    tts_text = speech_text[:500] if len(speech_text) > 500 else speech_text
    log.info(f"TTS generating: text_len={len(tts_text)}")

    response = await openai_client.audio.speech.create(
        model="tts-1",
        voice="onyx",  # Deep, warm male voice — good for Nigerian context
        input=tts_text,
        response_format="mp3",
        speed=0.95,  # Slightly slower for clarity
    )

    response.stream_to_file(output_path)

    file_size = os.path.getsize(output_path)
    log.info(f"TTS saved: {output_path} ({file_size} bytes)")
    if file_size == 0:
        os.remove(output_path)
        raise RuntimeError("OpenAI TTS produced empty audio file")

    return output_path
