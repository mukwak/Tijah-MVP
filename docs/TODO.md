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

- [x] **No privacy policy or consent flow (NDPR compliance)** (FIXED)
  Added: consent language in welcome message, privacy intent handler ("my privacy"), `/privacy` bilingual HTML page, "delete my data" handler with confirmation, report/receipt footer privacy links, pre-classifier patterns. NLU actions 27-28 added.

- [x] **No "quick daily total" recording** (FIXED)
  New `record_bulk_sale` handler: "I sold 20 thousand today" records a lump sum under "(general sales)". Gently nudges user to list items next time. NLU action 26 added.

- [x] **Long voice notes (>30s) sometimes truncated by Whisper** (FIXED)
  Three-layer approach: (1) TTS splits long replies into up to 3 voice note chunks at sentence boundaries with "check your text message" overflow redirect. (2) Very long voice notes (>45s) trigger echo-and-confirm -- transcription is echoed back and user confirms before processing. (3) One-time hint for long notes (>30s): "try sending shorter voice notes" fires once per user.

- [x] **No guided onboarding for voice-only users** (FIXED)
  First voice message from a new user gets a spoken intro prepended to the TTS reply: "I'm Tijah, your shop helper." so they hear it even if they can't read.

---

## Medium Priority (from Round 9)

- [x] **Discovery hints gated behind stock tracking (M7)** (FIXED)
  Discovery hints now fire by total sale count regardless of stock data. Sale 1: credits, sale 2: undo, sale 3: expenses, sale 4 (no stock): stock tracking, sale 5+: dynamic discovery, sale 12: backdate, sale 15: check sales, sale 20: weekly summary.
  Files: `app/handlers.py` (handle_record_sale hint logic)

- [x] **Weekly/monthly summary not discoverable (M8)** (FIXED)
  New `hint_discover_weekly` template fires at sale 20: "Try asking 'how was my week?' to see your progress."
  Files: `app/handlers.py`, `app/responses.py`

- [x] **Evening nudge lacks top seller insight (M9)** (FIXED)
  Evening nudge now includes top-selling product by revenue: "Your top seller today was rice (15,000 naira)." Excludes "(general sales)" bulk entries.
  Files: `app/main.py` (daily_nudge), `app/responses.py`

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

- [x] **Evening nudge "X sales" count is misleading for multi-sale users** (FIXED)
  Now uses `SUM(quantity)` instead of `COUNT(*)`. Template wording changed from "things"/"sales" to "items".

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

- [x] **No audio-only feature tips** (PARTIALLY FIXED)
  Nudges now send TTS audio for voice users. In-message hints are already spoken via the voice echo TTS reply. Remaining: standalone discovery tips could be more prominent in audio.

- [ ] **NLU may misparse corrections as new sales**
  "The price was 500 not 300" can be ambiguous — NLU might interpret as a new sale or a price-setting action instead of an edit. Needs stronger correction-detection patterns.
  *Affected user: Iya Sade.*
  Files: `app/nlu.py` (SYSTEM_PROMPT)

---

## From Simulation Round 4

### Medium Severity

- [x] **Payment + new credit in one message not supported** (FIXED)
  New `handle_payment_and_credit` handler + NLU action 30. "Alhaji Musa pay me 50k but buy shock absorber 22k on credit" now works in one message.

- [x] **No "did I already record today?" check** (FIXED)
  Pre-classifier now catches "what did I sell today" / "did I record". Discovery hint added at sale count 15 to surface the existing `check_sales` feature.

- [x] **Multi-sale with per-item credit still not supported** (FIXED)
  `multi_sale` items now support optional `customer` and `is_credit` fields. Credit notes preserved in multi-sale summaries.

### Low Severity

- [ ] **Whisper alias map doesn't cover industry-specific terms**
  Spare parts names ("alternator", "shock absorber", "ball joint") aren't in the alias map. Whisper variants like "auto nator" or "shoka bsorber" create duplicate products.
  *Affected user: Oga Segun.*
  Files: `app/handlers.py` (_PRODUCT_ALIASES)

- [ ] **No product split (reverse of merge)**
  Can merge "coca cola" into "coke" but can't split "rice" into "jollof rice" and "fried rice" by reclassifying old entries.
  *Affected user: Sister Funke.*
  Files: `app/handlers.py`

- [ ] **Profit label confusing for food vendors**
  Food vendors record ingredient purchases as expenses, not stock. Profit shows correctly (revenue - expenses) but label "Profit (after cost and expenses)" implies they're separate. Should adapt wording when cost data is absent.
  *Affected user: Sister Funke.*
  Files: `app/handlers.py` (handle_daily_summary), `app/responses.py`

- [ ] **Report page is HTML-only — no voice summary**
  Voice-only users get a report link but can't easily read the HTML page. A voice summary ("Your top 5 products this month are...") would be more accessible.
  *Affected user: Oga Segun.*
  Files: `app/handlers.py`, `app/main.py`

- [ ] **Shop name feature has zero discovery**
  None of the simulated users set their shop name. The hint exists but isn't triggered frequently enough. The shop name only shows on the report page header.
  *Affected users: All.*
  Files: `app/handlers.py` (_get_discovery_hint)

- [x] **"Check sales" (itemized list) not discoverable** (FIXED)
  Pre-classifier catches "what did I sell today". Discovery hint added at sale count 15. Confirmed working in Round 5 simulation.

---

## From Simulation Round 5

### Medium Severity — Multi-Sale Reliability (Priority: batch/end-of-day recording is a core use case)

Users often wait until they're done serving customers to record everything at once. Multi-sale MUST work smoothly for this workflow.

- [x] **Multi-sale with multiple missing prices only asks about one at a time** (FIXED)
  Multi-sale now saves unpriced items as pending. Lists all missing prices at once. When user sets a price, pending items with that product are auto-recorded.

- [x] **Setting price mid-multi-sale doesn't auto-complete pending items** (FIXED)
  `handle_set_price` now checks for `multi_sale_pending` actions. After setting a price, any pending items matching that product are auto-recorded. Remaining unpriced items stay pending with a prompt.

### Medium Severity — Other

- [x] **No way to retroactively mark a sale as credit ("that was on credit")** (FIXED)
  New `handle_mark_credit` handler + NLU action 31 (MARK_CREDIT). "That was on credit" / "na credit" finds the last non-credit sale, marks it as credit, and creates a credit record. Pre-classifier patterns added. Customer name fuzzy matching supported.

### Low Severity

- [ ] **No multi-customer multi-product in a single message**
  "I sold cement to Alhaji Musa and iron rod to Chief Bala" in one message isn't supported. Each customer requires a separate message. Acceptable for alpha.
  *Affected user: Alhaji Suleiman.*

- [ ] **Price changes don't prompt to update stored price**
  Selling at 5,500 when stored price is 5,000 doesn't ask "Should I update the price?" Next sale without a price still uses the old 5,000.
  *Affected user: Alhaji Suleiman.*
  Files: `app/handlers.py` (handle_record_sale)

- [ ] **Unit defaults to "piece" — awkward for services**
  Hair braiding recorded as "1 piece braiding" instead of "1 braiding". Services should default to no unit or "service".
  *Affected user: Ada.*
  Files: `app/handlers.py` (handle_record_sale)

- [ ] **Edit targets most recent sale only; no way to pick which one**
  "Change the braiding price" edits the most recent braiding sale. If user meant one from 3 days ago, no way to specify beyond `when`. Could confirm which sale before editing.
  *Affected user: Ada.*
  Files: `app/handlers.py` (handle_edit_last)

- [ ] **No month-over-month comparison view**
  "How did this month compare to last month?" only shows current month with a one-line insight. No side-by-side breakdown.
  *Affected user: Ada.*
  Files: `app/handlers.py` (handle_daily_summary)

---

## From Simulation Round 6

*No medium or high severity issues found. System is stable.*

### Low Severity

- [x] **Price ambiguity message echoes recalculated total, not user's original number** (FIXED)
  Handler now saves `raw_unit_price`/`raw_total` before recalculation and uses the user's original number in the clarification message.

- [x] **Stale pending actions fire on wrong context** (FIXED)
  New business actions now clear any old pending action before processing. Prevents "yes" from confirming a stale price clarification or customer match after the user moved on.

---

## From Clarification System Test (Round 7)

*10 users, 29 scenarios, 181 tests. All pass after M6 fix.*

### Medium Severity

- [x] **Customer fuzzy match false positives for equal-length names** (FIXED)
  `_find_similar_customer` used `min(a, b, key=len)` / `max(a, b, key=len)` to pick shorter/longer strings for character overlap comparison. When both names had the same character count (spaces removed), Python's `min`/`max` both returned the first argument — comparing a name to itself (100% match always). Any two customer names with equal length would trigger a false "Did you mean...?" prompt.
  *Example: "Mama Kike" (8 chars) falsely matched "Sisi Tayo" (8 chars).*
  Files: `app/handlers.py` (_find_similar_customer)

- [ ] **No multi-stock handler for restocking multiple products at once**
  "I bought 50 phone case, 30 charger, 20 power bank" requires 3 separate messages. High-volume shops restock many products at once.
  *Affected user: Emeka.*
  Files: `app/nlu.py`, `app/handlers.py`

- [ ] **No "all time" summary period**
  "How much have I made since I started?" has no answer. Only today/yesterday/week/month are supported. Users who've been on 3+ months want cumulative stats.
  *Affected user: Halima.*
  Files: `app/handlers.py` (handle_daily_summary), `app/nlu.py`

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
- [ ] **Voice report summary** — spoken overview of report data for voice-only users (Oga Segun)
- [ ] **Product split** — reclassify old entries when a product needs to be separated (Sister Funke)
- [ ] **Sales-by-customer report** — "How much has Alhaji Musa bought from me this month?" Total purchases (not just credit) per customer (Alhaji Suleiman)
- [ ] **Product variants** — sub-products like "box braids" vs "cornrow" under a parent "braiding" category (Ada)
- [x] **Smarter long voice note handling** (DONE) — TTS splits long replies into up to 3 voice note chunks; STT echo-and-confirm for very long notes (>45s); one-time hint for long notes (>30s). 306 tests with full DB verification.

---

## Stats from 3-Month User Simulation (Round 9)

*3 low-literate Nigerian users over 3 months of daily usage.*

| User | Type | Language | Sales | Revenue | Features Discovered |
|------|------|----------|:-----:|--------:|:-------------------:|
| Mama Efe | Food vendor | Pidgin | 16 | 145,000 | 18 |
| Oga Bayo | Provision store | English | 10 | 30,050 | 13 |
| Sister Nkechi | Hair salon | English | 15 | 99,500 | 16 |
| **Total** | | | **41** | **274,550** | |

### Key Findings

| Area | Result |
|------|--------|
| Onboarding | Welcome is short (<400 chars), mentions privacy, not overwhelming |
| Feature discovery | All users found 13-18 features organically via hints |
| Privacy | Both English and Pidgin users could access privacy info |
| Clarifications | Price ambiguity, credit ambiguity, fuzzy match all work correctly |
| DB accuracy | All 41 sales, credits, expenses, payments verified in DB |
| Data queries | Summaries, credit lists, sales checks all return accurate data |
| Cross-user isolation | No data leakage between users |
| **Issue found** | **M7: Discovery hints gated behind stock tracking** |

### Comparison vs Round 8

| Metric | Round 8 | Round 9 | Change |
|--------|:---:|:---:|:---:|
| Total tests | 306 | 408 | +33% coverage |
| Simulation depth | Single session | 3 months lifecycle | New |
| Users | 10 (single flow each) | 3 (full lifecycle) | Deeper |
| New issues found | 0 | 1 (M7: hint gating) | Found |

---

## Stats from Long Voice End-of-Day Test (Round 8)

*Full end-to-end test of long voice note handling with DB verification.*

| User | Type | Language | Key Flows Tested |
|------|------|----------|------------------|
| Mama Nkechi | Food vendor | English | Multi-sale echo-confirm, one-time hint |
| Iya Basira | Food vendor | Pidgin | Reject -> retry -> confirm, Pidgin hint |
| Brother Emeka | Hardware | English | 4-item multi-sale, then normal text sale |
| Sisi Kemi | Cosmetics | English | Abandon voice for text (no phantom sale) |
| Alhaji Musa | Auto parts | Pidgin | Reject -> confirm brake pad -> confirm shock absorber |
| Mama Adaeze | Provision | English | Credit sale: is_credit=1, credit record, customer name |
| Aunty Funke | Hair salon | English | Empty confirm guard, double-confirm = no duplicate |
| Pastor Grace | Bookshop | English | Text -> voice multi-sale -> text (mixed workflow) |
| Baba Tunde | Wholesale | English | 8-item text batch + 2-item voice batch, TTS splitting |
| Mama Chisom | Provision | Pidgin | Credit + cash voice, stale cleared by expense, hint persistence |

### DB Verification Summary

| Metric | Value |
|--------|:---:|
| Users | 10 |
| Total sales in DB | 29 |
| Grand revenue | 552,000 naira |
| Credit sales verified | 2 (is_credit, customer, credit record) |
| Expenses verified | 1 (2,000 naira) |
| Negative cases (no phantom records) | 4 (rejection, abandon, stale, double-confirm) |
| Cross-user isolation checks | 10 users verified independently |
| Total tests | 306 |

### Comparison vs Round 7

| Metric | Round 7 | Round 8 | Change |
|--------|:---:|:---:|:---:|
| Total tests | 181 | 306 | +69% coverage |
| DB verification | None | Full (sales, credits, expenses) | New |
| Long voice flows tested | 0 | 10 users, all paths | New |
| Revenue verification | None | 552,000 naira cross-checked | New |

---

## Stats from Clarification System Test (Round 7)

*Focused stress test of all clarification and confirmation flows.*

| User | Type | Language | Scenarios | Key Flows Tested |
|------|------|----------|:---------:|------------------|
| Mama Blessing | Food vendor | Pidgin | 4 | Price ambiguity (Pidgin), credit ambiguity (Pidgin), confirm cash |
| Emeka | Electronics | English | 2 | Price ambiguity: each path + total path |
| Alhaji Musa | Building materials | English | 3 | Fuzzy customer match: accept + reject, new customer creation |
| Sister Funke | Tailor | English | 2 | Mark credit: no customer + has customer |
| Oga Segun | Auto parts | Pidgin | 3 | Multi-sale 3 items (2 unpriced), sequential set_price auto-complete |
| Halima | Cosmetics | English | 3 | Stale pending (M5): price ambiguity -> new action -> confirm nothing |
| Ada | Hair salon | English | 3 | Credit ambiguity -> credit, voice name correction + rename |
| Brother Chidi | Wholesale | English | 3 | Payment+credit combo fuzzy match, delete data cancel |
| Iya Sade | Food vendor | Pidgin | 3 | Reject fuzzy match, back-to-back clarifications |
| Mama Ngozi | Provision store | English | 5 | Stale customer pending, statement fuzzy match, mark credit fuzzy |

### Comparison vs Round 6

| Metric | Round 6 | Round 7 | Change |
|--------|:---:|:---:|:---:|
| New medium issues found | 0 | 1 (M6: fuzzy match bug) | Found + fixed |
| Total tests | 116 | 181 | +56% coverage |
| Clarification flows tested | Basic | All paths (price/credit/customer/stale/voice) | Comprehensive |
| Users tested | 3 | 10 | Broader diversity |

---

## Stats from Simulation Round 6

| Metric | Iya Blessing | Emeka | Halima |
|--------|:---:|:---:|:---:|
| Features discovered | 10/15 | 14/15 | 13/15 |
| Would recommend | Yes | Yes (3 referrals) | Yes |
| Would pay | 300-500/mo | 2-3k/mo | 1-2k/mo |
| Usage frequency | Daily | Daily | Daily |
| Retention risk | Very low | Very low | Very low |
| Top frustration | None | Price not auto-updating | Voice misheard "ankara" |

### Comparison vs Simulation Round 5

| Metric | Round 5 | Round 6 | Change |
|--------|:---:|:---:|:---:|
| New medium issues found | 3 | 0 | All clear |
| New low issues found | 5 | 3 | Fewer |
| Multi-sale batch flow | Broke on missing prices | Smooth with auto-complete | Fixed |
| Retroactive credit | Not possible | Works | Fixed |
| Recommend rate | 3/3 | 3/3 | Maintained |
| Retention risk (worst) | Low | Very low | Improved |

---

## Stats from Simulation Round 5

| Metric | Mama Ngozi | Alhaji Suleiman | Ada |
|--------|:---:|:---:|:---:|
| Features discovered | 12/15 | 13/15 | 14/15 |
| Would recommend | Yes (referred a friend) | Yes | Yes (already referred) |
| Would pay | 500-1k/mo | 3-5k/mo | 1-2k/mo |
| Usage frequency | Daily | Daily | Daily |
| Retention risk | Very low | Low | Very low |
| Top frustration | Long voice notes | Can't mark sale as credit after recording | "piece" unit for services |

### Comparison vs Simulation Round 4

| Metric | Round 4 | Round 5 | Change |
|--------|:---:|:---:|:---:|
| Avg features discovered | 16.7/22+ | 13/15 | Stable (fewer total features counted) |
| Clarification flows | N/A (not implemented) | Working (price + credit) | New |
| Payment+credit combo | Not supported | Working | New |
| Silent assumptions | Price + credit | None | Fixed |
| Recommend rate | 3/3 | 3/3 | Maintained |
| Retention risk (worst) | Low-medium | Low | Improved |

---

## Stats from Simulation Round 4

| Metric | Mama Blessing | Oga Segun | Sister Funke |
|--------|:---:|:---:|:---:|
| Features discovered | 17/22+ | 16/22+ | 17/22+ |
| Would recommend | Yes (already did) | Yes | Yes |
| Would pay | 1-2k/mo | 3-5k/mo | 500-1k/mo |
| Usage frequency | Daily | Daily | Daily |
| Retention risk | Very low | Low-medium | Low |
| Top frustration | None significant | Can't combine payment+credit | Profit label confusing |

### Comparison vs Simulation Round 2

| Metric | Round 2 | Round 4 | Change |
|--------|:---:|:---:|:---:|
| Avg features discovered | 16.3/20+ | 16.7/22+ | Stable (more features available) |
| Lowest user discovery | 13/20+ | 16/22+ | Improved |
| Voice user engagement | Low (text nudges ignored) | High (TTS nudges work) | Major improvement |
| Recommend rate | 3/3 | 3/3 | Maintained |
| Retention risk (worst) | Low-medium | Low-medium | Stable |

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
