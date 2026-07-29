# Tijah MVP - Issue Backlog

From 3-month user simulation (July 2026). Prioritized by severity and user impact.

---

## Critical

- [ ] **Voice name correction creates duplicate entries**
  When the voice name check hint fires ("I heard X — if wrong, type the correct spelling") and the user re-sends the full command with the correct name, it records a duplicate entry. The hint needs to guide users to say "the name is X" (rename) or Tijah should detect re-sends and auto-replace instead of double-recording.
  *Affected user: Iya Kemi. Caused her to abandon credit tracking.*
  Files: `app/handlers.py` (handle_record_credit), `app/responses.py` (hint_voice_name_check)

---

## High Priority

- [ ] **No batch/end-of-day recording for high-volume shops**
  Small shops with 30-50 daily transactions (200-naira soft drinks, biscuits) can't send a voice note per sale. Need support for: "Today I sold 20 coke at 200, 15 biscuit at 100, 10 soap at 300" as a single batch. multi_sale partially handles this but needs explicit batch UX and messaging.
  *Affected user: Iya Kemi. Only captured ~40% of her revenue.*
  Files: `app/nlu.py`, `app/handlers.py` (handle_multi_sale)

- [ ] **Can't fix old mistakes — undo/edit only targets the most recent entry**
  "Undo the rice sale" targets the most recent rice sale, but users can't fix something from 3 sales ago or from yesterday. Need time-range or ordinal targeting: "delete the rice sale from yesterday", "fix the second sale today".
  *Affected user: Mama Blessing. Noticed wrong price days later, couldn't fix it.*
  Files: `app/handlers.py` (handle_undo, handle_edit_last), `app/nlu.py`

- [ ] **Ambiguous pricing — "3 bags for 25 thousand" (each or total?)**
  When the user says "3 bags for 25 thousand", Tijah guesses whether it's 25k total or 25k each. Often guesses wrong. Should ask for confirmation when the math is ambiguous (quantity > 1 and a round price is given without "each"/"per").
  *Affected user: Mama Blessing. Records were silently wrong.*
  Files: `app/nlu.py` (SYSTEM_PROMPT), `app/handlers.py` (handle_record_sale)

---

## Medium Priority

- [ ] **No profit/margin view in summary**
  For products where both cost_price (from stock entry) and sell_price (from sales) exist, the daily/weekly summary should show: "Profit: X naira" (revenue minus cost-of-goods-sold). Currently only shows revenue minus expenses.
  *Affected user: Emeka. His top feature request. Would pay for it.*
  Files: `app/handlers.py` (handle_daily_summary)

- [ ] **No morning prompt / opening reminder**
  Only the evening nudge exists. Users forget to record sales during the day. A morning nudge ("Good morning! Ready to record today's sales") would prime the habit loop.
  *Affected user: Mama Blessing. Forgot ~50% of sales in month 1.*
  Files: `app/main.py` (daily_nudge endpoint or new morning endpoint), `app/responses.py`

- [ ] **Improve voice name correction flow**
  Current hint says "type the correct spelling" which leads users to re-send the entire command (creating duplicates). Should say: "If wrong, say 'the name is Sisi Tolu' — I'll fix it, not add a new one." Or auto-detect that the next message looks like a correction of the previous credit.
  *Affected user: Iya Kemi.*
  Files: `app/responses.py` (hint_voice_name_check), `app/handlers.py`

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

- [ ] **Profit tracking** — "How much profit did I make today?" (Emeka)
- [ ] **Batch recording** — "I sold 20 coke, 15 biscuit, 10 soap today" as end-of-day summary (Iya Kemi)
- [ ] **Morning reminder** — prompt at shop opening time (Mama Blessing)
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
