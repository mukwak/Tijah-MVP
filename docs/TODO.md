# Tijah MVP - Issue Backlog

From 3-month user simulation (July 2026). Prioritized by severity and user impact.

---

## Critical

- [x] **Voice name correction creates duplicate entries** (FIXED)
  Hint now guides users to say "change X to Y". Auto-detects duplicate credits (same amount, different name) and renames instead of adding.

---

## High Priority

- [ ] **No batch/end-of-day recording for high-volume shops**
  Small shops with 30-50 daily transactions (200-naira soft drinks, biscuits) can't send a voice note per sale. Need support for: "Today I sold 20 coke at 200, 15 biscuit at 100, 10 soap at 300" as a single batch. multi_sale partially handles this but needs explicit batch UX and messaging.
  *Affected user: Iya Kemi. Only captured ~40% of her revenue.*
  Files: `app/nlu.py`, `app/handlers.py` (handle_multi_sale)

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

- [ ] **Product name drift across voice sessions**
  User says "coke" one day, "coca cola" the next, "soft drink" another time. Gemini normalizes some but not all. Creates duplicate products in the database. The NLU prompt has normalization rules but they don't cover all cases. Consider post-NLU product name canonicalization or merging.
  *Affected user: Iya Kemi.*
  Files: `app/nlu.py` (SYSTEM_PROMPT normalization rules), `app/handlers.py` (_find_product)

- [ ] **Report page not optimized for small screens**
  The HTML report works but tables are hard to read on budget Android phones with small screens. Needs mobile-first responsive layout, larger text, and simpler formatting.
  *Affected user: Mama Blessing.*
  Files: `app/report.py` (render_report_html)

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

- [ ] **No payment summary / payment history view**
  "How much did customers pay me this week?" has no direct answer. Payments are embedded in the credit flow. Need a standalone payment summary.
  *Affected user: Emeka.*
  Files: `app/handlers.py`, `app/nlu.py`

- [ ] **Low-literate users don't discover most features**
  Iya Kemi discovered only 5 of 15+ features after 3 months. Progressive hints help moderate users but the lowest-literacy users ignore text hints in voice replies. Consider: audio-only tips, simpler hint language, or a guided "what else can I do?" flow.
  *Affected user: Iya Kemi.*
  Files: `app/responses.py` (all hint templates), `app/voice.py` (_make_speakable)

- [ ] **No way to merge duplicate products**
  If "coke" and "coca cola" both exist as separate products, there's no way to merge them. Need: "coke and coca cola are the same thing" or an admin-level product merge.
  *Affected user: Iya Kemi.*
  Files: `app/handlers.py`, `app/nlu.py`

- [ ] **Evening nudge timing not configurable**
  The cron endpoint fires when the external service calls it. Users in different time zones or with different shop hours can't customize when they get nudged.
  *Low impact for alpha, matters at scale.*
  Files: `app/main.py` (daily_nudge)

---

## Feature Requests (from simulated users)

- [x] **Profit tracking** — "How much profit did I make today?" (Emeka) (DONE)
- [ ] **Batch recording** — "I sold 20 coke, 15 biscuit, 10 soap today" as end-of-day summary (Iya Kemi)
- [x] **Morning reminder** — prompt at shop opening time (Mama Blessing) (DONE)
- [ ] **Inventory alerts** — "Your cement is running low, only 10 bags left" sent proactively (Emeka)
- [ ] **Payment summary** — "How much did people pay me this week?" (Emeka)
- [ ] **Product merge** — "Coke and Coca Cola are the same thing" (Iya Kemi)
- [ ] **Photo receipt** — take a photo of a handwritten receipt and have Tijah extract it (Mama Blessing)
- [ ] **Debt aging** — "Mama Joy has owed you for 30 days" warning (Emeka)

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
