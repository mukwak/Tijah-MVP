import os
from dotenv import load_dotenv

load_dotenv()

# WhatsApp (Meta Cloud API)
WHATSAPP_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "tijah_verify_2024")
WHATSAPP_APP_SECRET = os.getenv("META_APP_SECRET", "")

# OpenAI (Whisper)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Anthropic (Claude for NLU)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Database
DB_PATH = os.getenv("DB_PATH", "tijah.db")

# Audio cache directory
AUDIO_CACHE_DIR = os.getenv("AUDIO_CACHE_DIR", "audio_cache")
