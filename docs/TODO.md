# Tijah MVP - Issue Backlog

From 3-month user simulations (July 2026). Prioritized by severity and user impact.

---

## Critical

- [x] **Voice name correction creates duplicate entries** (FIXED)
  Hint now guides users to say "change X to Y". Auto-detects duplicate credits (same amount, different name) and renames instead of adding.

---

## High Priority

- [x] **No batch/end-of-day recording for high-volume shops** (FIXED)
  multi_sale now handles batch recording with optional prices: "I sold 20 coke, 15 biscuit, 10 soap" — looks up stored prices, reports items needing pricing. NLU updated to allow omitting prices.

- [x] **Can't fix old mistakes — undo/edit only targets the most recent entry** (FIXED)
  Undo and edit now accept optional `when` field: "delete the rice sale from yesterday". Combined with product filter for precise targeting.

- [x] **Ambiguous pricing — "3 bags for 25 thousand" (each or total?)** (FIXED)
  Sale confirmation now shows unit price when qty > 1: "Sold! 3 bag rice at 8,333 each = 25,000 naira". NLU prompt updated with explicit disambiguation rules.

---

## Medium Priority

- [x] **No profit/margin view in summary** (FIXED)
  Summary now shows "Profit (after cost and expenses): X naira" when cost data exists from stock entries.

- [x] **No morning prompt / opening reminder** (FIXED)
  New `/cron/morning-nudge?token=X` endpoint sends "Good morning! Ready to record today's sales" to active users.

- [x] **Improve voice name correction flow** (FIXED)
  Covered by the critical fix above — hint changed + duplicate detection added.

- [x] **Product name drift across voice sessions** (FIXED)
  Added post-NLU alias mapping table (`_PRODUCT_ALIASES`) for common variants. Expanded NLU normalization rules. Combined with merge_products feature for manual cleanup.

- [x] **Report page not optimized for small screens** (FIXED)
  Added `box-sizing: border-box`, base font 16px, scrollable `.table-wrap` divs, table font bumped to 0.9rem, tighter padding for mobile readability.

- [x] **No "quick daily total" recording** (FIXED)
  New `record_bulk_sale` handler: "I sold 20 thousand today" records a lump sum under "(general sales)". Gently nudges user to list items next time. NLU action 26 added.

- [x] **Long voice notes (>30s) sometimes truncated by Whisper** (FIXED)
  Detects long audio (>40KB) and appends hint: "That was a long voice note. If I missed anything, send a shorter follow-up."

- [x] **No guided onboarding for voice-only users** (FIXED)
  First voice message from a new user gets a spoken intro prepended to the TTS reply: "I'm Tijah, your shop helper." so they hear it even if they can't read.

---

## Low Priority

- [ ] **Multi-sale doesn't support per-item credit/customer**
  Can't say "I sold 30 bags cement to Alhaji Musa on credit, 20 bags to Chief Obi on credit" in one message. Each credit sale to a different customer requires a separate message.
  *Affected user: Brother Chidi.*
  Files: `app/nlu.py`, `app/handlers.py` (handle_multi_sale)

- [ ] **No product variants (size, type)**
  No way to distinguish "1/2 inch iron rod" from "3/4 inch iron rod" as variants of the same product. User has to create completely separate product names as a workaround.
  *Affected user: Brother Chidi.*
  Files: `app/handlers.py`, `app/database.py` (products table)

- [x] **No payment summary / payment history view** (FIXED)
  New `check_payments` handler with period filtering and per-customer breakdown. NLU action 22 added.

- [x] **Low-literate users don't discover most features** (FIXED)
  New `what_can_you_do` handler shows personalized list of unused features. Pre-classified for "what else" / "what can you do". Shows max 6 simple tips based on what the user hasn't tried yet.

- [x] **No way to merge duplicate products** (FIXED)
  New `merge_products` handler: "coke and coca cola are the same thing" merges all sales, stock entries, and quantities. NLU action 24 added.

- [ ] **Evening nudge timing not configurable**
  The cron endpoint fires when the external service calls it. Users in different time zones or with different shop hours can't customize when they get nudged.
  *Low impact for alpha, matters at scale.*
  Files: `app/main.py` (daily_nudge)

- [ ] **Evening nudge "X sales" count is misleading for multi-sale users**
  Counts sale records, not individual items. A user who sends 2 multi-sale voice notes recording 60 plates sees "2 sales" in the nudge. The total revenue is correct but the count is confusing.
  *Affected user: Iya Sade.*
  Files: `app/main.py` (daily_nudge)

- [ ] **No product categories/grouping**
  As product list grows past 10+ items, stock check and report become unwieldy. No way to group products (e.g. "drinks", "food", "building materials").
  *Affected user: Mama Adaeze.*
  Files: `app/database.py` (products table), `app/handlers.py`, `app/report.py`

- [ ] **Profit trend not shown in summary**
  Summary compares sales total to previous period but not profit. Users who care about profit want "your profit this week vs last week."
  *Affected user: Brother Chidi.*
  Files: `app/handlers.py` (handle_daily_summary)

- [ ] **No per-product profitability view**
  "Which product makes me the most money?" has no answer. Users want to see margin per product, not just revenue.
  *Affected user: Brother Chidi.*
  Files: `app/handlers.py`, `app/nlu.py`

- [ ] **Whisper transcription variants still create product duplicates**
  "Fry rice" vs "fried rice", "suya meat" vs "suya" — accent/pronunciation variants not covered by the alias map. Need a broader fuzzy product alias strategy or auto-merge suggestion.
  *Affected user: Iya Sade.*
  Files: `app/handlers.py` (_PRODUCT_ALIASES, _normalize_product_name)

- [ ] **No audio-only feature tips**
  Voice-only users ignore text hints appended after the voice echo. Feature discovery tips should be spoken in the TTS reply, not just appended as text.
  *Affected user: Iya Sade.*
  Files: `app/main.py` (_send_response), `app/voice.py`

- [ ] **NLU may misparse corrections as new sales**
  "The price was 500 not 300" can be ambiguous — NLU might interpret as a new sale or a price-setting action instead of an edit. Needs stronger correction-detection patterns.
  *Affected user: Iya Sade.*
  Files: `app/nlu.py` (SYSTEM_PROMPT)

---

## Feature Requests (from simulated users)

- [x] **Profit tracking** — "How much profit did I make today?" (Chidi) (DONE)
- [x] **Batch recording** — "I sold 20 coke, 15 biscuit, 10 soap today" as end-of-day summary (Iya Sade) (DONE)
- [x] **Morning reminder** — prompt at shop opening time (Mama Adaeze) (DONE)
- [x] **Inventory alerts** — "Your cement is running low, only 10 bags left" sent proactively (Chidi) (DONE)
- [x] **Payment summary** — "How much did people pay me this week?" (Chidi) (DONE)
- [x] **Product merge** — "Coke and Coca Cola are the same thing" (Iya Sade) (DONE)
- [ ] **Photo receipt** — take a photo of a handwritten receipt and have Tijah extract it (Mama Adaeze)
- [x] **Debt aging** — "Mama Joy has owed you for 30 days" warning (Chidi) (DONE)
- [x] **Quick daily total** — "I sold 20 thousand today" without listing items (Mama Adaeze, Iya Sade) (DONE)
- [ ] **Export to Excel/PDF** — download records for printing or sharing (Chidi)
- [ ] **Supplier tracking** — "I bought from supplier X" for purchase attribution (Chidi)
- [ ] **Profit per product** — "Which product makes me the most money?" (Chidi)
- [x] **Voice-guided onboarding** — audio walkthrough for first-time voice users (Iya Sade) (DONE)

---

## Stats from Simulation Round 2

| Metric | Mama Adaeze | Brother Chidi | Iya Sade |
|--------|:---:|:---:|:---:|
| Features discovered | 16/20+ | 20/20+ | 13/20+ |
| Would recommend | Yes | Yes, strongly | Yes, if shown how |
| Would pay | 500-1000/mo | 2000-5000/mo | 200-500/mo |
| Usage frequency | Daily | Daily | Daily |
| Retention risk | Low | Very low | Low-medium |
| Top frustration | Product list too long | Multi-customer credit sales | Long voice notes truncated |

### Comparison vs Simulation Round 1

| Metric | Round 1 | Round 2 | Change |
|--------|:---:|:---:|:---:|
| Avg features discovered | 8.7/15 | 16.3/20+ | ~2x |
| Lowest-literate user discovery | 5/15 | 13/20+ | 2.6x |
| Recommend rate | 2/3 definite | 3/3 | Better |
| Voice name duplicates | Critical | Solved | Fixed |
| Retention risk (worst) | Medium-high | Low-medium | Improved |
