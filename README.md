# Tijah - Voice-First WhatsApp Shop Manager

Tijah is a WhatsApp-based shop assistant for informal traders in Nigeria. Traders send voice notes or text messages to record sales, track stock, manage credit, and monitor expenses — no app download required.

## Quick Start (Local)

```bash
# 1. Clone and set up
git clone <repo-url> && cd Tijah_MVP
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env   # Then fill in your API keys (see Environment Variables below)

# 3. Run the CLI simulator (no WhatsApp needed)
python test_local.py
```

## Architecture

```
WhatsApp User
     |
     | voice note / text
     v
Meta Cloud API (v21.0)
     |
     v
FastAPI Webhook (/webhook)
     |
     +---> Audio? ---> OpenAI Whisper (STT) ---> text
     |
     v
Pre-classifier (regex, fast)
     |
     +---> match? ---> Intent JSON
     |
     +---> no match ---> Gemini 2.0 Flash (NLU) ---> Intent JSON
     |
     v
Handler (business logic)
     |
     v
SQLite (local) / Neon Postgres (hosted)
     |
     v
Response (text + optional TTS via edge-tts)
     |
     v
WhatsApp reply (text message + voice note if user sent voice)
```

## Features

| Feature | Example command |
|---------|----------------|
| Record sales | "I sold 3 bags of rice for 5000 each" |
| Batch sales | "I sold 20 coke, 15 biscuit, 10 soap" |
| Buy stock | "I bought 10 bags of cement at 3000" |
| Credit book | "Mama Joy owes me 5000" |
| Track payments | "Mama Joy paid 2000" |
| Retroactive credit | "That was on credit" (marks last sale) |
| Expenses | "I spent 500 on transport" / "3k on flour and 1.5k on oil" |
| Set prices | "Rice is 5000 per bag" |
| Daily/weekly/monthly summary | "How did my shop do today/this week/this month?" |
| Sales list | "What did I sell this week?" |
| Payment history | "How much did people pay me this week?" |
| Stock check | "How much rice do I have?" |
| Undo / edit | "Cancel that" / "Undo the rice sale" / "It was 3 not 5" |
| Backdate | "I sold rice yesterday" / "I sold cement on Saturday" |
| Merge products | "Coke and coca cola are the same thing" |
| Shop report | "My report" (generates a shareable web link) |
| Customer receipt | "Receipt for Mama Joy" (shareable proof of debt) |
| Privacy / delete data | "My privacy" / "Delete my data" |
| Language | Understands English and Nigerian Pidgin |

## Project Structure

```
app/
  main.py         - FastAPI app, webhook handler, message routing
  nlu.py          - Intent parsing (Gemini Flash)
  preclassifier.py - Fast regex pre-classifier (skips LLM for simple intents)
  handlers.py     - Business logic for all actions
  responses.py    - Bilingual response templates (English + Pidgin)
  voice.py        - OpenAI Whisper STT + edge-tts TTS
  whatsapp.py     - WhatsApp Cloud API client
  database.py     - DB layer (SQLite locally, Postgres in production)
  report.py       - Shareable HTML report pages
  config.py       - Environment variable loading
test_local.py     - CLI simulator for local testing
test_smoke.py     - End-to-end smoke tests (409 tests)
render.yaml       - Render deployment blueprint
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `META_ACCESS_TOKEN` | Yes | WhatsApp Cloud API token |
| `META_PHONE_NUMBER_ID` | Yes | WhatsApp phone number ID |
| `META_VERIFY_TOKEN` | Yes | Webhook verification token |
| `META_APP_SECRET` | Yes | App secret for signature verification |
| `GOOGLE_AI_API_KEY` | Yes | Google AI API key (Gemini Flash) |
| `OPENAI_API_KEY` | Yes | OpenAI key (Whisper STT) |
| `DATABASE_URL` | Production | Neon Postgres connection string (omit for local SQLite) |
| `BASE_URL` | Production | Public URL of deployed app |
| `ADMIN_TOKEN` | Optional | Enables admin dashboard at `/admin/{token}` |

## Deployment

The app is configured for Render free tier via `render.yaml`. See [ALPHA_SETUP.md](ALPHA_SETUP.md) for full deployment instructions.

```bash
# Deploy to Render
# 1. Connect GitHub repo to Render
# 2. Use render.yaml blueprint
# 3. Set environment variables in Render dashboard
```

## Testing

```bash
# Smoke tests (409 tests, no API keys needed)
python test_smoke.py

# CLI simulator (text only, uses local SQLite)
# Uses the same pre-classifier + NLU pipeline as production
python test_local.py

# Run the server locally
uvicorn app.main:app --reload

# Verify Neon DB connection
python scripts/verify_neon.py
```

## License

Proprietary. All rights reserved.
