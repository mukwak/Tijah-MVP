# Changelog

## Alpha 0.4 - July 2026

### Voice Nudges for Voice-Only Users
- Tracks `voice_user` flag in shops table (set when user sends a voice note)
- Evening and morning nudges now send TTS audio alongside text for voice users
- Ensures voice-only users who can't read still receive nudge content

### Summary Unit Count Fix
- Daily summary and evening nudge now count total items sold (`SUM(quantity)`) instead of sale records (`COUNT(*)`)
- "3 bags of rice" now counts as 3 items, not 1
- Template wording changed from "things" to "items"

### Day-Name Backdating
- `_resolve_when` now supports day names: "saturday", "last friday", etc.
- NLU prompt updated to extract day names into the `when` field
- "I sold rice on Saturday" now correctly backdates to last Saturday

### Multi-Expense Recording
- New `handle_multi_expense` handler: "I spent 3k on flour and 1.5k on oil" records both
- NLU action 29 (MULTI_EXPENSE) added with items array format
- Shows itemized list with total after recording

### Voice Name Duplicate Prevention (Critical Fix)
- Voice name check hint now guides users to say "change X to Y" instead of re-sending the command
- Auto-detects when a credit with the same amount but different customer name follows a voice name check — renames instead of creating a duplicate
- Added `_peek_pending`/`_clear_pending` helpers for non-destructive pending action reads
- Guarded `confirm_yes`/`confirm_no` against unexpected pending action types

### Ambiguous Pricing Fix
- Sale confirmation now shows unit price when quantity > 1: "Sold! 3 bag rice at 5,000 each = 15,000 naira"
- NLU prompt updated with explicit price disambiguation rules ("each" vs "total" vs ambiguous)

### Time-Range Undo & Edit
- `handle_undo` and `handle_edit_last` now accept optional `when` field
- "Delete the rice sale from yesterday" or "fix yesterday's cement" now works
- NLU prompt updated to extract `when` for undo/edit_last actions

### Profit/Margin in Summary
- Daily/weekly/monthly summary now shows profit when cost data exists from stock entries
- "Profit (after cost and expenses): X naira" — revenue minus COGS minus expenses

### Morning Nudge
- New `/cron/morning-nudge?token=X` endpoint sends "Good morning! Ready to record today's sales" to active users
- Complements the existing evening nudge to prime daily recording habits

### Product Name Drift Prevention
- Added post-NLU alias mapping table (`_PRODUCT_ALIASES`) covering 15+ common variants (coca cola→coke, sachet water→water, etc.)
- Expanded NLU normalization rules for Nigerian market products
- `_normalize_product_name` now applies alias mapping after stripping unit qualifiers

### Report Mobile Optimization
- Added `box-sizing: border-box`, base font 16px, scrollable `.table-wrap` divs
- Table font bumped to 0.9rem with tighter padding for budget Android screens
- Applied to both shop report and per-customer receipt pages

### Payment Summary
- New `check_payments` handler: "How much did people pay me this week?"
- Per-customer breakdown by period (today/yesterday/week/month)
- NLU action 22 (CHECK_PAYMENTS) added

### Product Merge
- New `merge_products` handler: "Coke and coca cola are the same thing"
- Merges all sales, stock entries, and stock quantities from old product into new
- Deletes the old product record after merging
- NLU action 24 (MERGE_PRODUCTS) added

### Batch Recording Improvements
- `handle_multi_sale` now handles items without prices — looks up stored prices automatically
- Reports items that need pricing separately so user can set prices and re-record

### Feature Discoverability ("What can you do?")
- New `what_can_you_do` handler shows personalized list of unused features
- Pre-classified for "what else" / "what can you do" / "wetin you fit do"
- Shows max 6 simple tips based on what the user hasn't tried yet
- NLU action 11b added

### Debt Aging in Evening Nudge
- Evening nudge now mentions the oldest unpaid debt (>14 days old)
- "Mama Joy has owed you 5,000 naira for 21 days" with prompt to send reminder
- Surfaces the credit reminder feature naturally

### Low Stock Alerts in Evening Nudge
- Evening nudge now warns about products with stock ≤ 5 units
- "Low stock alert: cement (3 bag left). Time to restock!"
- Only triggers for products that have stock tracking enabled

### Quick Daily Total ("Bulk Sale")
- New `record_bulk_sale` handler: "I sold 20 thousand today" records a lump sum
- Stored under "(general sales)" product — counts toward revenue and summaries
- Gently nudges user to list specific items next time for better tracking
- NLU action 26 (RECORD_BULK_SALE) added

### Long Voice Note Warning
- Detects voice notes >40KB (~30+ seconds) and appends a hint
- "That was a long voice note. If I missed anything, send a shorter follow-up"
- Prevents users from losing data without knowing it

### Privacy & Data Controls (NDPR Compliance)
- Welcome message now includes consent language: "By sending me messages, you agree..."
- New `privacy` handler: "my privacy" / "is my data safe?" returns plain-language summary
- New `/privacy` HTML page with English/Pidgin toggle — explains what's stored, why, who sees it
- New `delete_data` handler: "delete my data" with yes/no confirmation, then wipes all records
- Report and receipt page footers now link to `/privacy`
- Pre-classifier catches "my privacy", "delete my data", "is my data safe", etc.
- NLU actions 27 (PRIVACY) and 28 (DELETE_DATA) added

### Voice Onboarding for New Users
- First voice message from a new user gets a spoken intro prepended to the TTS reply
- "I'm Tijah, your shop helper." is heard aloud, not just read as text
- Ensures voice-only users who can't read still hear the introduction

---

## Alpha 0.3 - July 2026

### Voice Name Accuracy
- Whisper prompt enhanced with Nigerian name prefixes (Mama, Alhaji, Brother, Sister, Chief, etc.) and 20 common Nigerian names to reduce transcription errors
- Voice name verification: when a voice user records credit for a NEW customer, Tijah hints "I heard X — if that's wrong, type the correct spelling"
- Voice payment lookup: when a voice user's customer name isn't found, Tijah suggests typing the name instead

### Product Name Normalization
- New `_normalize_product_name()` strips unit qualifiers before matching — "bag of rice" → "rice", "crate of minerals" → "minerals"
- Prevents NLU-generated verbose product names from creating duplicate products in the database

### Edit & Undo by Product
- `handle_edit_last` now accepts an optional `product` field — "change the rice to 4 bags" targets the most recent rice sale, not just the most recent sale overall
- `handle_undo` now accepts an optional `product` field — "undo the cement sale" deletes only the matching product's sale
- NLU prompt updated to extract product name for edit_last and undo actions

---

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
