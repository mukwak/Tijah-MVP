"""Voice processing: Speech-to-Text (Whisper) and Text-to-Speech (edge-tts)."""
import logging
import re
import tempfile
import os
import hashlib
import edge_tts
from openai import AsyncOpenAI
from app.config import OPENAI_API_KEY, AUDIO_CACHE_DIR

log = logging.getLogger("tijah")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# edge-tts Nigerian English voices (free, natural-sounding)
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-NG-EzinneNeural")  # Female Nigerian
# Alternative: "en-NG-AbeoNeural" for male Nigerian voice


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
                       "wetin I sell today, how my shop do. "
                       "Common name prefixes: Mama, Alhaji, Brother, Sister, Chief, "
                       "Mrs, Aunty, Uncle, Pastor, Iya, Baba. "
                       "Nigerian names: Nkechi, Chinyere, Adebayo, Oluwaseun, Tolu, "
                       "Emeka, Ngozi, Funke, Adamu, Amina, Kemi, Blessing, Joy, Grace, "
                       "Chiamaka, Obiora, Yemi, Nneka, Ifeoma, Chisom",
            )
        return transcript.text.strip()
    finally:
        os.unlink(tmp_path)


def _speak_number(m: re.Match) -> str:
    """Convert formatted numbers: 60,000 → 60 thousand, 1,500,000 → 1.5 million."""
    raw = m.group(0).replace(",", "")
    n = float(raw)
    if n >= 1_000_000:
        val = n / 1_000_000
        return f"{val:g} million"
    if n >= 1_000:
        val = n / 1_000
        return f"{val:g} thousand"
    return raw


def _make_speakable(text: str) -> str:
    """Convert formatted text into natural conversational sentences."""
    s = text

    # Strip the "I heard: ..." echo — already in the text message
    s = re.sub(r'I hear(?:d)?(?: you say)?:?\s*"[^"]*"\s*', '', s)

    # Never read URLs aloud — tell the user to press the link instead
    s = re.sub(r'https?://\S+', 'just press the link for the message I send you', s)

    # Convert numbers first so sentence rewrites match spoken numbers
    s = re.sub(r'\d{1,3}(?:,\d{3})+', _speak_number, s)

    # --- Sale ---
    # "Sold! 3 bag rice = 60 thousand naira" → "I've recorded a sale. 3 bag of rice for 60 thousand naira."
    s = re.sub(
        r'Sold!\s*(.+?)\s*=\s*(.+?\s*naira)',
        r"I've recorded a sale. \1 for \2.",
        s,
    )
    # Credit note on sale: "\nMama Joy bought on credit."
    s = s.replace(" bought on credit.", " bought it on credit.")
    s = s.replace(" buy am on credit.", " buy am on credit.")

    # --- Stock ---
    # "Stocked! 10 bag cement added." → "Got it. I've added 10 bag of cement to your stock."
    s = re.sub(
        r'Stocked!\s*(.+?)\s+added\.',
        r"Got it. I've added \1 to your stock.",
        s,
    )
    # "Cost: 35 thousand naira (3.5 thousand each)." → "That cost 35 thousand naira, 3.5 thousand each."
    s = re.sub(
        r'\s*Cost:\s*(.+?naira)\s*\((.+?)each\)\.',
        r' That cost \1, \2each.',
        s,
    )

    # --- Credits ---
    # "{customer} owes you {amount} naira.{note} Saved!"
    s = s.replace('Saved!', 'Got it, saved.')

    # --- Payments ---
    # "Still owing 10 thousand naira." → already a sentence

    # --- Summary ---
    # "Today you sold 5 things = 125 thousand naira." → "Today you sold 5 things for 125 thousand naira."
    s = re.sub(r'sold (\d+) things\s*=\s*', r'sold \1 things for ', s)
    # "Cash in hand: 110 thousand naira." → "You have 110 thousand naira cash in hand."
    s = re.sub(
        r'Cash (?:in hand|wey remain):\s*(.+?\s*naira)',
        r'You have \1 cash in hand',
        s,
    )

    # --- Price ---
    # "rice price set to 5 thousand naira per bag." → "I've set the price of rice to 5 thousand naira per bag."
    s = re.sub(
        r'(\w+) price set to (.+?naira per \w+)',
        r"I've set the price of \1 to \2",
        s,
    )

    # --- Lists: credit list, expense list, stock list ---
    # "Total: 45 thousand naira" → "That's 45 thousand naira in total." (before list items eat it)
    s = re.sub(r'\n\n\s*Total:\s*(.+?\s*naira)', r"\n\nThat's \1 in total.", s)
    s = re.sub(r'\nTotal:\s*(.+?\s*naira)', r"\nThat's \1 in total.", s)

    # Convert indented list items (before newlines are removed)
    # Top sellers: "  rice: 3 sold = 15 thousand naira" → "rice, 3 sold for 15 thousand naira."
    s = re.sub(r'\n\s+(\w[\w\s]*?):\s*(.+?)\s*=\s*(.+?naira)', r'\n\1, \2 for \3.', s)
    # List items: "\n  Name: amount naira" → "\nName, amount naira."
    s = re.sub(r'\n\s+(\w[\w\s]*?):\s*(.+?naira)', r'\n\1, \2.', s)
    # Other indented items (stock list without naira): "\n  rice: 5 bag"
    s = re.sub(r'\n\s+(\w)', r'\n\1', s)

    # List headers → sentences
    s = s.replace('People owing you:', 'People owing you.')
    s = s.replace('Your stock:', 'Here is your stock.')


    # --- Top sellers header ---
    s = s.replace('Top sellers:', 'Your top sellers are')
    s = s.replace('Wetin sell pass:', 'Wetin sell pass,')

    # --- Expenses ---
    # "Spent 5 thousand naira on transport. Saved!" → already handled by Saved! rule
    s = re.sub(r'You spent (\w+):\s*', r'You spent \1. ', s)

    # --- Remove list indentation ---
    s = re.sub(r'\n\s{2,}', '\n', s)

    # --- Hints: keep as-is, they're already sentences ---

    # Replace remaining newlines with natural pauses
    s = re.sub(r'\n{2,}', '. ', s)
    s = re.sub(r'\n', '. ', s)

    # Clean up punctuation
    s = re.sub(r':\s*\.', ': ', s)
    s = re.sub(r'[.,]\s*[.,]', '.', s)
    s = re.sub(r'\s+\.', '.', s)
    s = re.sub(r'  +', ' ', s)

    return s.strip()


async def text_to_speech(text: str, language: str = "english") -> str:
    """Convert text to speech using edge-tts (free, Nigerian English voice). Returns path to mp3 file."""
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

    # Truncate very long text
    tts_text = speech_text[:500] if len(speech_text) > 500 else speech_text
    log.info(f"TTS generating (edge-tts): text_len={len(tts_text)}, voice={EDGE_TTS_VOICE}")

    communicate = edge_tts.Communicate(tts_text, EDGE_TTS_VOICE, rate="-5%")
    await communicate.save(output_path)

    file_size = os.path.getsize(output_path)
    log.info(f"TTS saved: {output_path} ({file_size} bytes)")
    if file_size == 0:
        os.remove(output_path)
        raise RuntimeError("edge-tts produced empty audio file")

    return output_path
