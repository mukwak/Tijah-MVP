# Tijah - Architecture Overview

## System Diagram

```
+------------------+
|  Trader's Phone  |
|  (WhatsApp)      |
+--------+---------+
         |
         | voice note / text / button tap
         v
+------------------+
|  Meta Cloud API  |  WhatsApp Business Platform (v21.0)
|  (webhook)       |  Signature verification (HMAC SHA-256)
+--------+---------+
         |
         v
+------------------+
|  FastAPI App     |  Render free tier (uvicorn)
|  /webhook POST   |  Deduplicates messages (processed_messages table)
+--------+---------+
         |
         +-------> Audio message?
         |            |
         |            v
         |     +---------------+
         |     | OpenAI Whisper |  Speech-to-text
         |     | (whisper-1)    |  Prompt-tuned for Nigerian English/Pidgin
         |     +-------+-------+
         |             |
         |             v text
         |
         v
+------------------+
| Pre-classifier   |  Fast regex matching for simple intents
| (preclassifier)  |  (greetings, undo, help, report, language switch)
+--------+---------+
         |
         +-------> no match?
         |            |
         |            v
         |     +------------------+
         |     | Gemini 2.0 Flash |  Full NLU: extracts action, product,
         |     | (Google AI)      |  quantity, price, customer, etc.
         |     +--------+---------+  Returns structured JSON intent
         |              |
         v              v
+------------------+
| Intent Router    |  Maps action -> handler function
| (_route_intent)  |  22 supported actions
+--------+---------+
         |
         v
+------------------+
| Handler          |  Business logic (record sale, add stock, etc.)
| (handlers.py)    |  Reads/writes to database
+--------+---------+
         |
         v
+------------------+
| Database         |  SQLite (local dev) or Neon Postgres (production)
| (database.py)    |  asyncpg pool (min 0, max 5 connections)
+--------+---------+  Auto-creates tables on startup
         |
         v
+------------------+
| Response Builder |  Bilingual templates (English + Pidgin)
| (responses.py)   |  Follow-up hints drip-fed after each action
+--------+---------+
         |
         +-------> Voice reply needed? (user sent voice note)
         |            |
         |            v
         |     +------------------+
         |     | OpenAI TTS       |  gpt-4o-mini-tts, "onyx" voice
         |     | (voice.py)       |  Nigerian English accent instructions
         |     +--------+---------+  Cached by text hash
         |              |
         v              v
+------------------+
| WhatsApp Reply   |  Text message (always) + voice note (if voice input)
| (whatsapp.py)    |  Interactive buttons for confirmations
+------------------+
```

## Data Model

```
shops
  phone (PK), name, language, onboarded, created_at

products
  id (PK), phone, name, unit, stock_qty, cost_price, sell_price, created_at

sales
  id (PK), phone, product_id, product_name, quantity, unit_price, total, customer, is_credit, created_at

stock_entries
  id (PK), phone, product_id, product_name, quantity, cost_price, entry_type, created_at

credits
  id (PK), phone, customer, amount, paid, settled, note, created_at, updated_at

payments
  id (PK), phone, customer, amount, note, created_at

expenses
  id (PK), phone, description, amount, category, created_at

pending_actions
  phone (PK), action_data (JSON), created_at  -- confirmation flow state

processed_messages
  message_id (PK), created_at  -- webhook deduplication

report_tokens
  phone (PK), token (unique), created_at  -- shareable report links

feedback
  id (PK), phone, message, created_at  -- tester complaints

customer_receipts
  phone, customer, token (unique), created_at  -- per-customer receipt links
  UNIQUE(phone, customer)
```

## Key Design Decisions

**1. Regex pre-classifier before LLM**
Simple intents (greetings, undo, help) are matched with regex to skip the Gemini API call entirely. This saves cost and reduces latency for common messages.

**2. SQLite locally, Postgres in production**
`database.py` abstracts both behind the same interface. A `_translate_sqlite_query` function handles SQL dialect differences. This allows full local development without any external services.

**3. Voice echo-back**
When a user sends a voice note, the text reply starts with "I heard: {transcription}" so the user can verify Whisper got it right before trusting the recorded data.

**4. Never leave the user hanging**
Every code path returns a response. Errors send a friendly fallback message. Unrecognized intents get a help message. No silent failures.

**5. Language detection, not language setting**
The NLU detects whether the user is speaking English or Pidgin and responds in kind. Users don't need to configure anything — they just talk naturally.

**6. Stateless handlers, stateful undo**
Each handler is a pure function of (phone, intent, language). Undo reverses the last action by deleting the recorded row and restoring stock/credit state inline.

**7. Word-boundary product matching with normalization**
Product name lookup normalizes input first (strips unit qualifiers like "bag of", "crate of"), then tries exact match, then word-boundary fuzzy matching for names 4+ characters. This prevents "rice" from colliding with "fried rice", "bag of rice" from creating a duplicate of "rice", while still allowing "cement" to match "cement bag".

**8. Helpfulness-first onboarding**
New users are NOT blocked with a welcome message before their first action is processed. If they send a business action (sale, credit), it's handled first and a brief intro is appended. If they send a greeting, the welcome IS the response.

**9. Progressive feature discovery**
Hints are drip-fed based on what features the user has NOT yet tried, not just message count. After enough sales, the system checks if expenses, stock, reports, or receipts have been used and nudges toward the most relevant next feature.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/webhook` | Meta webhook verification |
| POST | `/webhook` | Incoming WhatsApp messages |
| GET | `/health` | Health check |
| GET | `/report/{token}` | Shareable shop report (HTML) |
| GET | `/receipt/{token}` | Per-customer receipt page (HTML) |
| GET | `/admin/{token}` | Admin dashboard (HTML) |
| GET | `/cron/daily-nudge?token=X` | Evening summary sender (external cron) |

## External Services

| Service | Used For | Cost |
|---------|----------|------|
| Meta WhatsApp Cloud API | Send/receive messages | Free (test number, 5 recipients) |
| OpenAI Whisper (whisper-1) | Voice transcription | ~$0.006/min |
| Google Gemini 2.0 Flash | Intent parsing (NLU) | Free tier / ~$0.001/msg |
| OpenAI TTS (gpt-4o-mini-tts) | Voice replies | ~$0.015/reply |
| Neon Postgres | Production database | Free tier |
| Render | App hosting | Free tier |
