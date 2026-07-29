# Tijah MVP - Issue Backlog

From 3-month user simulation (July 2026). Prioritized by severity and user impact.

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

---

## Low Priority

- [ ] **Multi-sale doesn't support per-item credit/customer**
  Can't say "I sold 30 bags cement to Alhaji Musa on credit, 20 bags to Chief Obi on credit" in one message. Each credit sale to a different customer requires a separate message.
  *Affected user: Emeka.*
  Files: `app/nlu.py`, `app/handlers.py` (handle_multi_sale)

- [ ] **No product variants (size, type)**
  No way to distinguish "1/2 inch iron rod" from "3/4 inch iron rod" as variants of the same product. User has to create completely separate product names as a workaround.
  *Affected user: Emeka.*
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

---

## Feature Requests (from simulated users)

- [x] **Profit tracking** — "How much profit did I make today?" (Emeka) (DONE)
- [x] **Batch recording** — "I sold 20 coke, 15 biscuit, 10 soap today" as end-of-day summary (Iya Kemi) (DONE)
- [x] **Morning reminder** — prompt at shop opening time (Mama Blessing) (DONE)
- [x] **Inventory alerts** — "Your cement is running low, only 10 bags left" sent proactively (Emeka) (DONE)
- [x] **Payment summary** — "How much did people pay me this week?" (Emeka) (DONE)
- [x] **Product merge** — "Coke and Coca Cola are the same thing" (Iya Kemi) (DONE)
- [ ] **Photo receipt** — take a photo of a handwritten receipt and have Tijah extract it (Mama Blessing)
- [x] **Debt aging** — "Mama Joy has owed you for 30 days" warning (Emeka) (DONE)

---

## Stats from Simulation

| Metric | Mama Blessing | Emeka | Iya Kemi |
|--------|:---:|:---:|:---:|
| Features discovered | 8/15 | 13/15 | 5/15 |
| Would recommend | Yes | Yes, strongly | Maybe |
| Would pay | 500-1000/mo | 2000-5000/mo | 200-500/mo |
| Usage frequency | Daily | Daily | 3-4x/week |
| Retention risk | Low | Very low | Medium-high |
| Top frustration | Can't fix old mistakes | No profit view | Too many messages for small sales |
