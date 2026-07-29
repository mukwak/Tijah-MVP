# Changelog

## Alpha 0.2 - July 2026

### Onboarding (rewritten)
- Helpfulness-first: if a new user sends a business action (sale, credit, etc.), it's processed immediately and a brief intro is appended — no blocking welcome wall
- If a new user sends a greeting, a shorter welcome message IS the response (one message, not two)
- Welcome shortened from 4 paragraphs to 3 lines + privacy note

### New Features
- **Per-customer receipt:** "receipt for Mama Joy" generates a shareable link showing only that customer's credit/payment history — safe to send to the customer as proof
- **Daily nudge endpoint:** `/cron/daily-nudge?token=ADMIN_TOKEN` sends evening summaries to active users (call from external cron service like cron-job.org)
- **Progressive feature discovery:** hints now continue beyond the first 3 sales, surfacing expenses, stock tracking, reports, receipts, and backdating at wider intervals based on which features the user hasn't tried yet

### Improvements
- Product fuzzy matching tightened: word-boundary matching prevents "rice" from colliding with "fried rice"; short names (< 4 chars) require exact match
- NLU prompt action numbering fixed (was duplicated at #15)
- CLI test simulator (`test_local.py`) now uses pre-classifier before Gemini, matching production flow
- Credit recording hints now also surface credit reminders and customer receipts at higher usage counts

### New Endpoints
- `GET /receipt/{token}` — per-customer receipt page (HTML)
- `GET /cron/daily-nudge?token=X` — evening summary sender

---

## Alpha 0.1 - July 2026

### Core
- WhatsApp webhook with Meta signature verification
- Message deduplication (persistent, survives restarts)
- Auto-onboarding: new users get a welcome message on first contact
- Shop naming: "My shop is called Blessing Store"

### Sales & Stock
- Record sales by voice or text with product, quantity, and price
- Automatic price memory for repeat products
- Credit sales (customer bought but hasn't paid)
- Multi-item sales in a single message
- Stock tracking: buy stock, check levels, auto-decrement on sale
- Price setting: "Rice is 5000 per bag"

### Credit Book
- Record debts: "Mama Joy owes me 5000"
- Record payments: "Mama Joy paid 2000"
- Check all credits: "Who owes me?"
- Credit history per customer
- Edit credit amounts
- Customer name matching with confirmation prompts

### Expenses
- Record expenses with categories (rent, transport, electricity, etc.)
- Check expenses by period

### Reports & Summaries
- Daily, weekly, and monthly summaries (sales, expenses, profit, top sellers)
- Shareable web report via tokenized link ("my report")
- Admin dashboard for monitoring all shops

### Voice
- Speech-to-text via OpenAI Whisper (tuned for Nigerian English/Pidgin)
- Text-to-speech via OpenAI gpt-4o-mini-tts (Nigerian English accent)
- Voice echo-back: "I heard: ..." so users can verify transcription
- Voice reply only when user sends a voice note

### UX
- Bilingual: English + Nigerian Pidgin (auto-detected, switchable)
- Default to English; Pidgin only when mirroring user
- Follow-up hints after each action (drip-fed, not walls of text)
- Undo / cancel last action
- Edit last entry: "It was 3 bags not 5"
- Interactive button prompts for confirmations
- No dead-end errors: always responds with something helpful
- Feedback intent: "I have a complaint"

### Infrastructure
- FastAPI on Render free tier
- SQLite (local dev) / Neon Postgres (production)
- asyncpg connection pool with retry
- CLI test simulator (`test_local.py`)
