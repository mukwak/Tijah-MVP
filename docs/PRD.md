# Tijah - Product Requirements Document

**Version:** 0.1 (Alpha)
**Last updated:** July 2026

---

## 1. Problem

Millions of informal traders in Nigeria (market women, kiosk owners, small shop operators) run their businesses without any record-keeping. They track sales, stock, and debts in their heads or in notebooks that get lost.

This causes real problems:
- They don't know if they're making or losing money
- Customers deny debts with no proof
- Stock runs out unexpectedly
- They can't grow because they can't see what's working

Existing solutions (POS apps, accounting software) fail this audience because:
- Many traders have low literacy or are more comfortable speaking than typing
- Smartphone storage is limited; they avoid downloading apps
- The tools are designed for formal businesses, not someone selling bags of rice from a shop

## 2. Solution

Tijah is a WhatsApp shop assistant. Traders talk to it like a person — by voice note or text — and it keeps their records automatically.

**Why WhatsApp?** It's already on every trader's phone. No download, no sign-up, no learning curve.

**Why voice-first?** Many traders are more comfortable speaking than typing. Voice notes are how they already communicate on WhatsApp.

## 3. Target User

**Primary:** Informal traders in Nigerian markets and neighborhoods.

- Sells physical goods (food, building materials, household items, cosmetics)
- Revenue: N50,000 - N2,000,000/month
- Age: 25-55
- Smartphone owner (Android, mostly)
- Comfortable with WhatsApp voice notes
- May have limited literacy; prefers speaking to typing
- Keeps records in head or paper notebook (or not at all)

**Language:** Nigerian English and Nigerian Pidgin (code-switching is common)

## 4. Core Features (Alpha)

### 4.1 Sales Recording
User says what they sold, quantity, and price. Tijah records the sale and confirms.
- Supports unit prices and totals
- Remembers prices for repeat products
- Handles credit sales (customer bought but hasn't paid)

### 4.2 Stock Management
User records when they buy/receive stock. Tijah tracks quantities.
- Stock decreases automatically when sales are recorded
- "How much rice do I have?" shows current levels

### 4.3 Credit Book
Tracks who owes the user money and how much.
- Records new debts
- Records partial or full payments
- "Who owes me?" shows all outstanding credits
- Payment history per customer

### 4.4 Expense Tracking
Records business expenses by category (rent, transport, electricity, supplies, etc.).

### 4.5 Daily/Weekly/Monthly Summary
"How did my shop do today?" returns total sales, expenses, profit, cash in hand, and top sellers.

### 4.6 Shareable Report
"My report" generates a private web link with a full view of sales, stock, credits, and expenses. The link is tokenized (unguessable) and auto-updates.

### 4.7 Per-Customer Receipt
"Receipt for Mama Joy" generates a shareable web link showing only that customer's credit and payment history. Safe to send directly to the customer as proof of debt. Shows total bought, total paid, and current balance with clear visual status.

### 4.8 Daily Nudge
An evening summary sent proactively via cron to active users. Shows what they recorded today and prompts for anything missed. Keeps users engaged without requiring them to remember to check.

### 4.9 Undo / Edit
"Cancel that" undoes the last action. Users can also correct quantities and amounts.

### 4.10 Voice In, Voice Out
If the user sends a voice note, Tijah replies with both text and a voice note (using natural Nigerian English TTS). The text reply echoes back what was heard so the user can verify accuracy.

### 4.11 Bilingual Support
Defaults to English. Switches to Pidgin when the user speaks Pidgin. User can also explicitly switch ("speak pidgin" / "speak english").

## 5. Current Limitations (Alpha)

- WhatsApp test number: max 5 pre-approved recipient phone numbers
- Render free tier: cold start up to ~60 seconds after 15 min idle
- Neon free tier: 0.5 GB storage, DB suspends after 5 min idle (auto-reconnects)
- No image/document/location message support (text and voice only)
- No automated tests (manual testing only via `test_local.py` and live WhatsApp)

## 6. Non-Goals (Alpha)

- Multi-user shops / staff accounts
- Inventory alerts / reorder reminders
- Payments / mobile money integration
- Receipt generation
- Supplier management
- WhatsApp Business catalog integration
- iOS / Android native app

## 7. Technical Architecture

| Layer | Technology |
|-------|-----------|
| Interface | WhatsApp Cloud API (Meta) |
| Backend | Python / FastAPI |
| STT | OpenAI Whisper |
| NLU | Regex pre-classifier + Gemini 2.0 Flash |
| TTS | OpenAI gpt-4o-mini-tts |
| Database | SQLite (local) / Neon Postgres (production) |
| Hosting | Render (free tier) |

### Cost Structure (per message, estimated)
- **Text message:** ~$0.001 (Gemini Flash NLU only; free tier covers early users)
- **Voice message:** ~$0.006/min (Whisper STT) + $0.001 (NLU) + ~$0.015 (TTS reply)
- **Pre-classified message:** $0 (regex match skips all AI calls)
- **Hosting:** Free (Render free tier + Neon free tier)

## 8. Success Metrics

### Alpha (current phase)
- 5-10 real traders complete a full testing session
- Users can record sales, check credits, and get summaries without help
- Tijah correctly understands >80% of voice messages on first try
- Users say they would use it for their real shop

### Post-Alpha
- Daily active users sending >3 messages/day
- Retention: >50% weekly return rate
- Net Promoter Score >40

## 9. Risks

| Risk | Mitigation |
|------|-----------|
| Whisper misunderstands Nigerian accents/Pidgin | Prompt engineering; echo-back for user verification |
| Cold start latency on Render free tier | Warn users; upgrade to paid tier at scale |
| Users send unexpected message types (images, locations) | Graceful fallback responses; never leave user hanging |
| Credit disputes ("I never owe am") | Per-customer receipt link as proof; read-only shareable report |
| Data privacy concerns | Records are per-phone, private by default; report links are unguessable tokens |

## 10. Roadmap

**Alpha (now):** Core recording, voice support, WhatsApp delivery, manual testing with real traders.

**Beta:** Inventory alerts, daily summary auto-send, multi-period reports, onboarding improvements.

**v1:** Payment integration (bank transfers / mobile money), receipt generation, growth to 100+ users.

**Future:** Multi-staff shops, supplier orders, business insights ("your best day is Saturday"), USSD fallback for non-smartphone users.
