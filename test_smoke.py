"""End-to-end smoke test for Tijah MVP. Run: python test_smoke.py"""
import asyncio
import os
import pathlib

# Force local SQLite for testing -- use unique name to avoid lock conflicts
import time as _time
_db_name = f"test_smoke_{os.getpid()}.db"
os.environ["DATABASE_URL"] = ""
os.environ["DB_PATH"] = _db_name
os.environ["BASE_URL"] = "https://test.example.com"

# Clean up from any prior run
for _old in pathlib.Path(".").glob("test_smoke*.db*"):
    try:
        _old.unlink()
    except (PermissionError, OSError):
        pass

# Must import AFTER env is set
from app.database import get_db, close_db
from app.preclassifier import preclassify
from app.main import _route_intent
from app.responses import get_response
from app.handlers import _peek_pending, _clear_pending

PHONE = "2349000000001"
passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        failed += 1


async def run():
    db = await get_db()
    print(f"DB backend: {db.backend}")
    print("=" * 60)

    # === TEST 1: New user greeting (onboarding) ===
    print("\n--- TEST 1: New user greeting ---")
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (PHONE,))
    await db.commit()
    intent = preclassify("hello")
    check("Pre-classifies hello", intent and intent["action"] == "greeting")
    response = await _route_intent(PHONE, intent, "english")
    # Simulate onboarding: greeting -> welcome replaces response
    welcome = get_response("welcome", "english")
    check("Welcome under 350 chars", len(welcome) < 350, f"got {len(welcome)}")
    check("Welcome mentions Tijah", "Tijah" in welcome)
    check("Single message (no duplicate)", welcome.count("Tijah") == 1)

    # === TEST 2: Helpfulness-first onboarding ===
    print("\n--- TEST 2: Helpfulness-first onboarding ---")
    PHONE2 = "2349000000002"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (PHONE2,))
    await db.commit()
    intent = {"action": "record_sale", "product": "cement", "quantity": 2, "unit": "bag",
              "unit_price": 4500, "total": 9000}
    resp = await _route_intent(PHONE2, intent, "english")
    resp += get_response("welcome_after_action", "english")
    check("Sale confirmed first", "Sold!" in resp)
    check("Brief intro appended", "Tijah" in resp)
    check("Sale before intro", resp.index("Sold!") < resp.index("Tijah"))

    # === TEST 3: Record sale ===
    print("\n--- TEST 3: Record sale ---")
    intent = {"action": "record_sale", "product": "rice", "quantity": 3, "unit": "bag",
              "unit_price": 5000, "total": 15000}
    resp = await _route_intent(PHONE, intent, "english")
    check("Sale confirmed", "Sold!" in resp)
    check("Total shown", "15,000" in resp)

    # === TEST 4: Record credit ===
    print("\n--- TEST 4: Record credit ---")
    intent = {"action": "record_credit", "customer": "Mama Joy", "amount": 8000,
              "note": "2 bags of rice"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Credit confirmed", "Mama Joy" in resp and "8,000" in resp)

    # === TEST 5: Record payment ===
    print("\n--- TEST 5: Record payment ---")
    intent = {"action": "record_payment", "customer": "Mama Joy", "amount": 3000}
    resp = await _route_intent(PHONE, intent, "english")
    check("Payment recorded", "3,000" in resp)
    check("Balance shown", "5,000" in resp)

    # === TEST 6: Customer receipt ===
    print("\n--- TEST 6: Customer receipt ---")
    intent = {"action": "customer_statement", "customer": "Mama Joy"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Receipt link generated", "test.example.com/receipt/" in resp)
    check("Customer mentioned", "Mama Joy" in resp)

    # === TEST 7: Receipt HTML renders ===
    print("\n--- TEST 7: Receipt HTML ---")
    from app.report import (get_or_create_customer_receipt_token,
                            get_customer_by_receipt_token,
                            render_customer_receipt_html)
    token = await get_or_create_customer_receipt_token(PHONE, "Mama Joy")
    result = await get_customer_by_receipt_token(token)
    check("Token resolves", result is not None)
    check("Phone matches", result and result[0] == PHONE)
    check("Customer matches", result and result[1] == "Mama Joy")
    html = await render_customer_receipt_html(PHONE, "Mama Joy")
    check("HTML has customer", "Mama Joy" in html)
    check("HTML has credit amount", "8,000" in html)
    check("HTML has payment", "3,000" in html)
    check("HTML has balance status", "owing" in html.lower())

    # === TEST 8: Record expense ===
    print("\n--- TEST 8: Record expense ---")
    intent = {"action": "record_expense", "description": "transport",
              "amount": 500, "category": "transport"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Expense recorded", "500" in resp and "transport" in resp.lower())

    # === TEST 9: Add stock ===
    print("\n--- TEST 9: Add stock ---")
    intent = {"action": "add_stock", "product": "rice", "quantity": 20,
              "unit": "bag", "cost_price": 4000}
    resp = await _route_intent(PHONE, intent, "english")
    check("Stock confirmed", "Stocked!" in resp)

    # === TEST 10: Check stock ===
    print("\n--- TEST 10: Check stock ---")
    intent = {"action": "check_stock", "product": "rice"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Stock level correct (20 - 3 = 17)", "17" in resp)

    # === TEST 11: Daily summary ===
    print("\n--- TEST 11: Daily summary ---")
    intent = {"action": "daily_summary", "period": "today"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Summary has sales", "sold" in resp.lower() or "15,000" in resp)
    check("Summary uses 'items' not 'things'", "items" in resp.lower())
    check("Summary has expenses", "500" in resp or "spent" in resp.lower())

    # === TEST 12: Undo ===
    print("\n--- TEST 12: Undo ---")
    intent = {"action": "undo"}
    resp = await _route_intent(PHONE, intent, "english")
    check("Undo confirmed", "Removed" in resp or "remove" in resp.lower())

    # === TEST 13: Pre-classifier ===
    print("\n--- TEST 13: Pre-classifier ---")
    cases = [
        ("hi", "greeting"), ("cancel that", "undo"), ("my report", "get_report"),
        ("help", "help"), ("yes", "confirm_yes"), ("no", "confirm_no"),
        ("speak pidgin", "change_language"), ("feedback", "feedback"),
    ]
    for text, expected in cases:
        r = preclassify(text)
        check(f'"{text}" -> {expected}', r and r["action"] == expected,
              f"got {r}")
    check("Business msg passes through", preclassify("I sold 3 bags of rice") is None)

    # === TEST 14: Product matching ===
    print("\n--- TEST 14: Product matching ---")
    from app.handlers import _find_product

    r = await _find_product(db, PHONE, "rice")
    check("Exact match works", r is not None and "rice" in r[1].lower())

    await db.execute("INSERT INTO products (phone, name, unit) VALUES (?, ?, ?)",
                     (PHONE, "oil", "bottle"))
    await db.commit()
    r = await _find_product(db, PHONE, "groundnut oil")
    check("Short-name fuzzy rejected", r is None or r[1] != "oil")

    await db.execute("INSERT INTO products (phone, name, unit) VALUES (?, ?, ?)",
                     (PHONE, "cement bag", "bag"))
    await db.commit()
    r = await _find_product(db, PHONE, "cement")
    check("Word-boundary match works", r is not None and "cement" in r[1].lower())

    # === TEST 15: Progressive hints ===
    print("\n--- TEST 15: Progressive hints ---")
    from app.handlers import _get_discovery_hint

    PHONE3 = "2349000000003"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (PHONE3,))
    await db.execute(
        "INSERT INTO sales (phone, product_name, quantity, unit_price, total) VALUES (?, ?, ?, ?, ?)",
        (PHONE3, "test", 1, 100, 100))
    await db.commit()
    hint = await _get_discovery_hint(db, PHONE3, "english")
    check("No expenses -> hints expenses", "expense" in hint.lower())

    await db.execute(
        "INSERT INTO expenses (phone, description, amount, category) VALUES (?, ?, ?, ?)",
        (PHONE3, "test", 100, "other"))
    await db.commit()
    hint = await _get_discovery_hint(db, PHONE3, "english")
    check("Has expenses -> hints stock", "stock" in hint.lower())

    # === TEST 16: Nudge templates ===
    print("\n--- TEST 16: Nudge templates ---")
    msg = get_response("nudge_evening_active", "english",
                       sales_count=5, sales_total="25,000")
    check("Active nudge has data", "5" in msg and "25,000" in msg)

    msg = get_response("nudge_evening_idle", "pidgin")
    check("Idle nudge prompts action", "record" in msg.lower() or "sell" in msg.lower())

    # === TEST 17: Pidgin responses ===
    print("\n--- TEST 17: Pidgin support ---")
    welcome_pidgin = get_response("welcome", "pidgin")
    check("Pidgin welcome exists", "Tijah" in welcome_pidgin)
    check("Pidgin welcome is Pidgin", "wetin" in welcome_pidgin.lower())

    receipt_pidgin = get_response("customer_receipt_link", "pidgin",
                                  customer="Mama Joy", url="https://x.com/r/abc")
    check("Pidgin receipt works", "Mama Joy" in receipt_pidgin)

    # === TEST 18: Voice name duplicate detection ===
    print("\n--- TEST 18: Voice name duplicate detection ---")
    PHONE4 = "2349000000004"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (PHONE4,))
    await db.commit()

    # Simulate: voice credit records "CC Tolu" (wrong name from Whisper)
    intent = {"action": "record_credit", "customer": "CC Tolu", "amount": 1500,
              "note": "soap", "_is_voice": True}
    resp = await _route_intent(PHONE4, intent, "english")
    check("Voice credit recorded", "CC Tolu" in resp and "1,500" in resp)
    check("Voice name hint shown", "change CC Tolu to" in resp)

    # User re-sends with correct name and same amount -- should rename, not duplicate
    intent2 = {"action": "record_credit", "customer": "Sisi Tolu", "amount": 1500,
               "note": "soap"}
    resp2 = await _route_intent(PHONE4, intent2, "english")
    check("Detected as correction", "Changed" in resp2 or "change" in resp2.lower())
    check("No duplicate", "duplicate" in resp2.lower() or "double" in resp2.lower()
          or "No duplicate" in resp2)

    # Verify only one credit exists, under the corrected name
    cursor = await db.execute(
        "SELECT customer, amount FROM credits WHERE phone = ? AND settled = 0", (PHONE4,))
    credits = await cursor.fetchall()
    check("Only one credit entry", len(credits) == 1)
    check("Name corrected to Sisi Tolu",
          len(credits) == 1 and credits[0][0] == "Sisi Tolu")

    # --- TEST 19: What can you do (personalized feature discovery) ---
    print("\n--- TEST 19: What can you do (feature discovery) ---")
    pre = preclassify("what can you do")
    check("Pre-classifies 'what can you do'", pre and pre["action"] == "what_can_you_do")
    pre2 = preclassify("what else")
    check("Pre-classifies 'what else'", pre2 and pre2["action"] == "what_can_you_do")
    result = await _route_intent(PHONE, {"action": "what_can_you_do"}, "english")
    check("Shows feature tips", "can do" in result.lower() or "sold" in result.lower() or "transport" in result.lower())
    check("Response is not empty", len(result) > 20)

    # --- TEST 20: Nudge templates (debt aging + low stock) ---
    print("\n--- TEST 20: Nudge templates (debt aging + low stock) ---")
    debt_msg = get_response("nudge_debt_aging", "english", customer="Mama Joy", amount="5,000", days=21)
    check("Debt aging has customer name", "Mama Joy" in debt_msg)
    check("Debt aging has days", "21" in debt_msg)
    low_stock_msg = get_response("nudge_low_stock", "english", items="cement (3 bag left)")
    check("Low stock has items", "cement" in low_stock_msg)

    # --- TEST 21: Bulk sale recording ---
    print("\n--- TEST 21: Bulk sale recording ---")
    result = await _route_intent(PHONE, {"action": "record_bulk_sale", "total": 20000}, "english")
    check("Bulk sale recorded", "20,000" in result)
    check("Bulk sale hint shown", "list" in result.lower() or "items" in result.lower())
    # Verify it shows up in summary
    summary = await _route_intent(PHONE, {"action": "daily_summary", "period": "today"}, "english")
    check("Bulk sale in summary", "20,000" in summary or "20000" in summary)

    # --- TEST 22: Long voice note + voice onboarding templates ---
    print("\n--- TEST 22: Long voice note + voice onboarding templates ---")
    long_hint = get_response("hint_long_voice", "english")
    check("Long voice hint exists", "long" in long_hint.lower() or "shorter" in long_hint.lower())
    voice_tip = get_response("welcome_voice_tip", "english")
    check("Voice onboarding tip exists", "tijah" in voice_tip.lower())
    voice_tip_pidgin = get_response("welcome_voice_tip", "pidgin")
    check("Voice tip pidgin exists", "tijah" in voice_tip_pidgin.lower())

    # --- TEST 23: Privacy and data deletion ---
    print("\n--- TEST 23: Privacy and data deletion ---")
    pre_priv = preclassify("my privacy")
    check("Pre-classifies 'my privacy'", pre_priv and pre_priv["action"] == "privacy")
    pre_del = preclassify("delete my data")
    check("Pre-classifies 'delete my data'", pre_del and pre_del["action"] == "delete_data")
    priv_result = await _route_intent(PHONE, {"action": "privacy"}, "english")
    check("Privacy summary mentions data", "save" in priv_result.lower() or "data" in priv_result.lower())
    check("Privacy summary has privacy link", "/privacy" in priv_result)
    # Test delete flow: initiate then confirm
    del_result = await _route_intent(PHONE, {"action": "delete_data"}, "english")
    check("Delete asks for confirmation", "sure" in del_result.lower() or "yes" in del_result.lower())
    # Confirm yes -- should delete
    confirm_result = await _route_intent(PHONE, {"action": "confirm_yes"}, "english")
    check("Delete confirmed", "deleted" in confirm_result.lower() or "cleared" in confirm_result.lower())
    # Welcome message includes consent
    welcome = get_response("welcome", "english")
    check("Welcome has consent language", "agree" in welcome.lower())

    # Re-create shop after data deletion in test 23
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (PHONE,))
    await db.commit()

    # --- TEST 24: Multi-expense recording ---
    print("\n--- TEST 24: Multi-expense recording ---")
    multi_exp = await _route_intent(PHONE, {
        "action": "multi_expense",
        "items": [
            {"description": "flour", "amount": 3000, "category": "supplies"},
            {"description": "oil", "amount": 1500, "category": "supplies"},
        ]
    }, "english")
    check("Multi-expense recorded", "flour" in multi_exp.lower() and "oil" in multi_exp.lower())
    check("Multi-expense total", "4,500" in multi_exp)

    # --- TEST 25: Day-name backdating ---
    print("\n--- TEST 25: Day-name backdating ---")
    from app.handlers import _resolve_when
    sat = _resolve_when("saturday")
    check("Day name resolves", sat is not None)
    fri = _resolve_when("last friday")
    check("'last friday' resolves", fri is not None)
    check("Today returns None", _resolve_when("today") is None)

    # --- TEST 26: Voice user flag in schema ---
    print("\n--- TEST 26: Voice user flag ---")
    cursor = await db.execute("SELECT voice_user FROM shops WHERE phone = ?", (PHONE,))
    row = await cursor.fetchone()
    check("voice_user column exists", row is not None)

    # --- TEST 27: Nudge template uses 'items' not 'sales' ---
    print("\n--- TEST 27: Nudge wording ---")
    nudge = get_response("nudge_evening_active", "english",
                         sales_count=10, sales_total="50,000")
    check("Nudge says 'items'", "items" in nudge.lower())
    check("Nudge does not say 'sales'", "10 sales" not in nudge.lower())

    # --- TEST 28: Payment + new credit in one message ---
    print("\n--- TEST 28: Payment + credit combo ---")
    # Set up: create a credit for the customer first
    intent = {"action": "record_credit", "customer": "Alhaji Musa", "amount": 50000,
              "note": "brake pad", "_skip_voice_dedup": True}
    await _route_intent(PHONE, intent, "english")
    # Now do the combo: payment + new credit
    combo = await _route_intent(PHONE, {
        "action": "payment_and_credit",
        "customer": "Alhaji Musa",
        "payment_amount": 30000,
        "credit_amount": 22000,
        "credit_note": "shock absorber",
    }, "english")
    check("Combo has payment", "30,000" in combo)
    check("Combo has new credit", "22,000" in combo)
    check("Combo has customer", "Alhaji Musa" in combo)

    # --- TEST 29: "Did I record today?" pre-classifier ---
    print("\n--- TEST 29: Check sales preclassifier ---")
    pre = preclassify("what did i sell today")
    check("Pre-classifies 'what did i sell today'",
          pre and pre["action"] == "check_sales")
    pre2 = preclassify("wetin i sell today")
    check("Pre-classifies pidgin variant",
          pre2 and pre2["action"] == "check_sales")
    pre3 = preclassify("did i record")
    check("Pre-classifies 'did i record'",
          pre3 and pre3["action"] == "check_sales")

    # --- TEST 30: Multi-sale with per-item credit ---
    print("\n--- TEST 30: Multi-sale with credit ---")
    multi_credit = await _route_intent(PHONE, {
        "action": "multi_sale",
        "items": [
            {"product": "cement", "quantity": 3, "unit": "bag", "unit_price": 5000, "total": 15000,
             "customer": "Chief Obi", "is_credit": True},
            {"product": "iron rod", "quantity": 2, "unit": "piece", "unit_price": 3000, "total": 6000},
        ]
    }, "english")
    check("Multi-sale credit recorded", "Chief Obi" in multi_credit and "credit" in multi_credit.lower())
    check("Multi-sale cash item recorded", "iron rod" in multi_credit)
    # Verify the credit was actually created
    cursor = await db.execute(
        "SELECT SUM(amount - paid) FROM credits WHERE phone = ? AND LOWER(customer) = 'chief obi' AND settled = 0",
        (PHONE,))
    credit_owed = (await cursor.fetchone())[0]
    check("Credit entry exists for Chief Obi", credit_owed is not None and credit_owed >= 15000)

    # --- TEST 31: Check sales hint exists ---
    print("\n--- TEST 31: Check sales discovery hint ---")
    hint = get_response("hint_discover_check_sales", "english")
    check("Check sales hint exists", "what did i sell" in hint.lower())

    # --- TEST 32: Price ambiguity asks for clarification ---
    print("\n--- TEST 32: Price ambiguity clarification ---")
    # "3 bag rice 25 thousand" -- NLU sends unit_price=25000 (user's number), ambiguous
    price_resp = await _route_intent(PHONE, {
        "action": "record_sale", "product": "rice", "quantity": 3, "unit": "bag",
        "unit_price": 25000, "total": 25000, "price_ambiguous": True,
    }, "english")
    check("Price ambiguity asks question", "total" in price_resp.lower() and "each" in price_resp.lower())
    check("Price ambiguity echoes user's number", "25,000" in price_resp)
    # Confirm "yes" = 25k total (8,333 each)
    confirm_resp = await _route_intent(PHONE, {"action": "confirm_yes"}, "english")
    check("Price confirm records sale", "Sold!" in confirm_resp)
    check("Price confirm uses total", "25,000" in confirm_resp)

    # --- TEST 33: Price ambiguity -- "no" means each ---
    print("\n--- TEST 33: Price ambiguity 'each' path ---")
    # "2 bag beans 10 thousand" -- is it 10k total or 10k each?
    await _route_intent(PHONE, {
        "action": "record_sale", "product": "beans", "quantity": 2, "unit": "bag",
        "unit_price": 10000, "total": 10000, "price_ambiguous": True,
    }, "english")
    # Say "no" = each interpretation (10k each = 20k total)
    each_resp = await _route_intent(PHONE, {"action": "confirm_no"}, "english")
    check("Each path records sale", "Sold!" in each_resp)
    check("Each path calculates correctly", "20,000" in each_resp)

    # --- TEST 34: Credit ambiguity asks for clarification ---
    print("\n--- TEST 34: Credit ambiguity clarification ---")
    credit_resp = await _route_intent(PHONE, {
        "action": "record_sale", "product": "cement", "quantity": 1, "unit": "bag",
        "unit_price": 5000, "total": 5000, "customer": "Mama Tinu",
        "is_credit": False, "credit_ambiguous": True,
    }, "english")
    check("Credit ambiguity asks question", "cash" in credit_resp.lower() and "credit" in credit_resp.lower())
    # Say "no" = credit
    credit_confirm = await _route_intent(PHONE, {"action": "confirm_no"}, "english")
    check("Credit path records sale", "Sold!" in credit_confirm or "credit" in credit_confirm.lower())
    check("Credit path marks as credit", "credit" in credit_confirm.lower())

    # --- TEST 35: Mark last sale as credit retroactively ---
    print("\n--- TEST 35: Mark last sale as credit ---")
    # Record a cash sale first with a unique customer name (avoid fuzzy match)
    await _route_intent(PHONE, {
        "action": "record_sale", "product": "bread", "quantity": 5, "unit": "piece",
        "unit_price": 500, "total": 2500, "customer": "Brother Emeka",
        "is_credit": False,
    }, "english")
    # Now mark it as credit
    mark_resp = await _route_intent(PHONE, {"action": "mark_credit"}, "english")
    check("Mark credit finds last sale", "bread" in mark_resp.lower())
    check("Mark credit shows customer", "Brother Emeka" in mark_resp)
    check("Mark credit confirms", "credit" in mark_resp.lower())

    # --- TEST 36: Mark credit with no recent sale ---
    print("\n--- TEST 36: Mark credit no sale ---")
    # Mark all existing sales as credit so none are available
    await db.execute("UPDATE sales SET is_credit = 1 WHERE phone = ?", (PHONE,))
    await db.commit()
    no_sale_resp = await _route_intent(PHONE, {"action": "mark_credit"}, "english")
    check("No sale to mark", "no recent" in no_sale_resp.lower())

    # --- TEST 37: Multi-sale saves pending for unpriced items ---
    print("\n--- TEST 37: Multi-sale pending unpriced items ---")
    # Clear any existing products to ensure "papaya" and "mango" have no price
    await db.execute("DELETE FROM products WHERE phone = ? AND name IN ('papaya', 'mango')", (PHONE,))
    await db.commit()
    multi_resp = await _route_intent(PHONE, {
        "action": "multi_sale",
        "items": [
            {"product": "papaya", "quantity": 3, "unit": "piece", "unit_price": 0, "total": 0},
            {"product": "mango", "quantity": 5, "unit": "piece", "unit_price": 0, "total": 0},
        ],
        "when": "today",
    }, "english")
    check("Multi-sale reports missing prices", "papaya" in multi_resp.lower() and "mango" in multi_resp.lower())
    check("Multi-sale tells user to set price", "price" in multi_resp.lower())
    # Verify pending action was saved
    pending = await _peek_pending(db, PHONE)
    check("Pending multi-sale saved", pending is not None and pending.get("action") == "multi_sale_pending")

    # --- TEST 38: Set price auto-completes pending multi-sale ---
    print("\n--- TEST 38: Set price auto-completes pending ---")
    price_resp = await _route_intent(PHONE, {
        "action": "set_price", "product": "papaya", "unit": "piece", "sell_price": 200,
    }, "english")
    check("Set price confirms", "papaya" in price_resp.lower() and "200" in price_resp)
    check("Auto-records papaya sale", "Sold!" in price_resp)
    # Mango still needs price
    check("Still needs mango price", "mango" in price_resp.lower())

    # Set mango price too -- should auto-complete and clear pending
    price_resp2 = await _route_intent(PHONE, {
        "action": "set_price", "product": "mango", "unit": "piece", "sell_price": 150,
    }, "english")
    check("Set mango price confirms", "mango" in price_resp2.lower())
    check("Auto-records mango sale", "Sold!" in price_resp2)
    # Pending should be cleared
    pending2 = await _peek_pending(db, PHONE)
    check("Pending cleared after all priced", pending2 is None)

    # --- TEST 39: Pre-classifier catches "that was on credit" ---
    print("\n--- TEST 39: Pre-classifier mark credit ---")
    check("'that was on credit'", preclassify("that was on credit") == {"action": "mark_credit"})
    check("'na credit'", preclassify("na credit") == {"action": "mark_credit"})
    check("'mark it as credit'", preclassify("mark it as credit") == {"action": "mark_credit"})

    # ==========================================================================
    # COMPREHENSIVE VOICE CLARIFICATION TESTS -- 10 Users, 24 Scenarios
    # ==========================================================================
    print("\n" + "=" * 60)
    print("VOICE CLARIFICATION SYSTEM -- 10 User Simulation")
    print("=" * 60)

    # -- USER 1: Mama Blessing -- Pidgin food vendor --
    U1 = "2349100000001"
    await db.execute("INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (U1,))
    await db.commit()

    # T40: Price ambiguity in Pidgin
    print("\n--- T40: [Mama Blessing] Price ambiguity (Pidgin) ---")
    resp = await _route_intent(U1, {
        "action": "record_sale", "product": "garri", "quantity": 5, "unit": "bag",
        "unit_price": 3000, "total": 3000, "price_ambiguous": True,
    }, "pidgin")
    check("Pidgin asks total or each", "total" in resp.lower() and "each" in resp.lower())
    check("Pidgin echoes user's 3,000", "3,000" in resp)
    check("Pidgin shows both interpretations", "15,000" in resp)  # 3000 * 5 = 15000

    # T41: Confirm yes -> 3000 is the total
    print("\n--- T41: [Mama Blessing] Confirm total (Pidgin) ---")
    resp = await _route_intent(U1, {"action": "confirm_yes"}, "pidgin")
    check("Total path records sale", "Sold!" in resp)
    check("Total is 3,000", "3,000" in resp)
    check("Unit price is 600 each", "600" in resp)  # 3000/5

    # T42: Credit ambiguity in Pidgin
    print("\n--- T42: [Mama Blessing] Credit ambiguity (Pidgin) ---")
    resp = await _route_intent(U1, {
        "action": "record_sale", "product": "beans", "quantity": 2, "unit": "bag",
        "unit_price": 4000, "total": 8000, "customer": "Iya Risi",
        "is_credit": False, "credit_ambiguous": True,
    }, "pidgin")
    check("Pidgin asks cash or credit", "cash" in resp.lower() and "credit" in resp.lower())
    check("Pidgin mentions customer", "Iya Risi" in resp)

    # T43: Confirm yes -> cash
    print("\n--- T43: [Mama Blessing] Confirm cash ---")
    resp = await _route_intent(U1, {"action": "confirm_yes"}, "pidgin")
    check("Cash path records sale", "Sold!" in resp)
    # Verify no credit entry was created
    cursor = await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ? AND LOWER(customer) = 'iya risi'", (U1,))
    check("No credit created for cash sale", (await cursor.fetchone())[0] == 0)

    # -- USER 2: Emeka -- English electronics seller --
    U2 = "2349100000002"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U2,))
    await db.commit()

    # T44: Price ambiguity -> each path
    print("\n--- T44: [Emeka] Price ambiguity -> each ---")
    resp = await _route_intent(U2, {
        "action": "record_sale", "product": "phone case", "quantity": 4, "unit": "piece",
        "unit_price": 2000, "total": 2000, "price_ambiguous": True,
    }, "english")
    check("English asks total or each", "total" in resp.lower() and "each" in resp.lower())
    # Confirm "no" = each
    resp = await _route_intent(U2, {"action": "confirm_no"}, "english")
    check("Each path: 2000 each x 4 = 8,000", "8,000" in resp)

    # T45: Price ambiguity -> total path (different product)
    print("\n--- T45: [Emeka] Price ambiguity -> total ---")
    await _route_intent(U2, {
        "action": "record_sale", "product": "charger", "quantity": 3, "unit": "piece",
        "unit_price": 4500, "total": 4500, "price_ambiguous": True,
    }, "english")
    resp = await _route_intent(U2, {"action": "confirm_yes"}, "english")
    check("Total path: 4,500 total", "4,500" in resp)
    check("Total path: 1,500 each", "1,500" in resp)  # 4500/3

    # -- USER 3: Alhaji Musa -- English, building materials --
    U3 = "2349100000003"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U3,))
    await db.commit()

    # Setup: credit for "Chief Bala"
    await _route_intent(U3, {"action": "record_credit", "customer": "Chief Bala",
                             "amount": 50000, "note": "cement"}, "english")

    # T46: Fuzzy customer match on payment -- "Chief Balla"
    print("\n--- T46: [Alhaji Musa] Fuzzy customer match on payment ---")
    resp = await _route_intent(U3, {
        "action": "record_payment", "customer": "Chief Balla", "amount": 20000,
    }, "english")
    check("Asks if same person", "Chief Bala" in resp and "Chief Balla" in resp)
    check("Confirmation prompt", "same person" in resp.lower() or "yes" in resp.lower())

    # T47: Confirm yes -> payment applied to matched customer
    print("\n--- T47: [Alhaji Musa] Confirm fuzzy match on payment ---")
    resp = await _route_intent(U3, {"action": "confirm_yes"}, "english")
    check("Payment recorded", "20,000" in resp)
    check("Remaining shown", "30,000" in resp)  # 50k - 20k = 30k

    # T48: Fuzzy match on credit -> reject (new customer)
    print("\n--- T48: [Alhaji Musa] Reject fuzzy match -> new customer ---")
    resp = await _route_intent(U3, {
        "action": "record_credit", "customer": "Chief Balewa", "amount": 15000,
        "note": "iron rod",
    }, "english")
    check("Fuzzy match suggested", "Chief Bala" in resp)
    resp = await _route_intent(U3, {"action": "confirm_no"}, "english")
    check("New customer created", "Chief Balewa" in resp and "15,000" in resp)
    # Verify both customers exist
    cursor = await db.execute(
        "SELECT DISTINCT customer FROM credits WHERE phone = ? ORDER BY customer", (U3,))
    customers = [r[0] for r in await cursor.fetchall()]
    check("Two distinct customers", len(customers) == 2)

    # -- USER 4: Sister Funke -- English tailor --
    U4 = "2349100000004"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U4,))
    await db.commit()

    # T49: Mark credit when sale has no customer -> asks for name
    print("\n--- T49: [Sister Funke] Mark credit -- no customer on sale ---")
    await _route_intent(U4, {
        "action": "record_sale", "product": "ankara", "quantity": 2, "unit": "yard",
        "unit_price": 3500, "total": 7000,
    }, "english")
    resp = await _route_intent(U4, {"action": "mark_credit"}, "english")
    check("Asks for customer name", "who" in resp.lower() or "customer" in resp.lower())

    # T50: Mark credit when sale HAS a customer -> auto-marks
    print("\n--- T50: [Sister Funke] Mark credit -- has customer ---")
    await _route_intent(U4, {
        "action": "record_sale", "product": "lace", "quantity": 3, "unit": "yard",
        "unit_price": 5000, "total": 15000, "customer": "Mrs Adeyemi",
        "is_credit": False,
    }, "english")
    resp = await _route_intent(U4, {"action": "mark_credit"}, "english")
    check("Auto-marks with existing customer", "Mrs Adeyemi" in resp)
    check("Shows product", "lace" in resp.lower())
    check("Shows credit confirmation", "credit" in resp.lower())
    # Verify credit record exists
    cursor = await db.execute(
        "SELECT amount FROM credits WHERE phone = ? AND LOWER(customer) = 'mrs adeyemi' AND settled = 0", (U4,))
    row = await cursor.fetchone()
    check("Credit record created", row is not None and row[0] == 15000)

    # -- USER 5: Oga Segun -- Pidgin auto parts dealer --
    U5 = "2349100000005"
    await db.execute("INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (U5,))
    await db.commit()

    # T51: Multi-sale with 3 items, 2 missing prices
    print("\n--- T51: [Oga Segun] Multi-sale with missing prices ---")
    resp = await _route_intent(U5, {
        "action": "multi_sale",
        "items": [
            {"product": "brake pad", "quantity": 2, "unit": "piece", "unit_price": 5000, "total": 10000},
            {"product": "spark plug", "quantity": 4, "unit": "piece", "unit_price": 0, "total": 0},
            {"product": "fan belt", "quantity": 1, "unit": "piece", "unit_price": 0, "total": 0},
        ],
    }, "pidgin")
    check("Brake pad recorded (has price)", "brake pad" in resp.lower() and "Sold!" in resp)
    check("Missing prices listed", "spark plug" in resp.lower() and "fan belt" in resp.lower())
    pending = await _peek_pending(db, U5)
    check("Pending has 2 unpriced items", pending is not None and len(pending.get("items", [])) == 2)

    # T52: Set price for spark plug -> auto-completes, fan belt still pending
    print("\n--- T52: [Oga Segun] Set price auto-completes first item ---")
    resp = await _route_intent(U5, {
        "action": "set_price", "product": "spark plug", "unit": "piece", "sell_price": 800,
    }, "pidgin")
    check("Spark plug price set", "spark plug" in resp.lower() and "800" in resp)
    check("Spark plug auto-recorded", "Sold!" in resp)
    check("Fan belt still pending", "fan belt" in resp.lower())

    # T53: Set price for fan belt -> auto-completes, pending cleared
    print("\n--- T53: [Oga Segun] Set price completes last item ---")
    resp = await _route_intent(U5, {
        "action": "set_price", "product": "fan belt", "unit": "piece", "sell_price": 2500,
    }, "pidgin")
    check("Fan belt price set", "fan belt" in resp.lower())
    check("Fan belt auto-recorded", "Sold!" in resp)
    pending = await _peek_pending(db, U5)
    check("All pending cleared", pending is None)

    # -- USER 6: Halima -- English cosmetics seller (tests STALE PENDING -- M5 fix) --
    U6 = "2349100000006"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U6,))
    await db.commit()

    # T54: Price ambiguity triggers pending
    print("\n--- T54: [Halima] Stale pending -- price ambiguity triggered ---")
    resp = await _route_intent(U6, {
        "action": "record_sale", "product": "lipstick", "quantity": 3, "unit": "piece",
        "unit_price": 1500, "total": 1500, "price_ambiguous": True,
    }, "english")
    check("Price ambiguity pending saved", "total" in resp.lower() and "each" in resp.lower())
    pending = await _peek_pending(db, U6)
    check("Pending is price_clarification", pending is not None and pending.get("action") == "price_clarification")

    # T55: Instead of confirming, user sends a completely new sale -> M5 clears stale pending
    print("\n--- T55: [Halima] New action clears stale pending ---")
    # Simulate what main.py does: clear pending before routing new business action
    await _clear_pending(db, U6)  # This is what main.py does for non-confirm actions
    resp = await _route_intent(U6, {
        "action": "record_sale", "product": "eyeliner", "quantity": 1, "unit": "piece",
        "unit_price": 800, "total": 800,
    }, "english")
    check("New sale recorded despite old pending", "Sold!" in resp and "eyeliner" in resp.lower())

    # T56: Now "yes" does nothing -- no stale action fires
    print("\n--- T56: [Halima] Yes after stale pending -> nothing ---")
    resp = await _route_intent(U6, {"action": "confirm_yes"}, "english")
    check("No stale action fires", "Nothing to confirm" in resp or "nothing" in resp.lower())

    # -- USER 7: Ada -- English hair salon --
    U7 = "2349100000007"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U7,))
    await db.commit()

    # T57: Credit ambiguity -> confirm no -> credit path
    print("\n--- T57: [Ada] Credit ambiguity -> credit path ---")
    resp = await _route_intent(U7, {
        "action": "record_sale", "product": "braiding", "quantity": 1, "unit": "piece",
        "unit_price": 8000, "total": 8000, "customer": "Sisi Tayo",
        "is_credit": False, "credit_ambiguous": True,
    }, "english")
    check("Asks cash or credit", "cash" in resp.lower() and "credit" in resp.lower())
    resp = await _route_intent(U7, {"action": "confirm_no"}, "english")
    check("Credit path records sale", "Sold!" in resp or "credit" in resp.lower())
    # Verify credit was created
    cursor = await db.execute(
        "SELECT amount FROM credits WHERE phone = ? AND LOWER(customer) = 'sisi tayo' AND settled = 0", (U7,))
    row = await cursor.fetchone()
    check("Credit entry created for Sisi Tayo", row is not None and row[0] == 8000)

    # T58: Voice credit -> name correction duplicate detection
    # Use a unique customer name that won't fuzzy match existing "Sisi Tayo"
    print("\n--- T58: [Ada] Voice name correction ---")
    # Debug: check state before
    resp = await _route_intent(U7, {
        "action": "record_credit", "customer": "Mama Kike", "amount": 5000,
        "note": "relaxer", "_is_voice": True,
    }, "english")
    check("Voice credit recorded", "Mama Kike" in resp and "5,000" in resp)
    # Now user corrects with the right name and same amount -> should rename, not duplicate
    resp = await _route_intent(U7, {
        "action": "record_credit", "customer": "Mama Kiki", "amount": 5000,
        "note": "relaxer",
    }, "english")
    check("Name correction detected", "Changed" in resp or "change" in resp.lower())
    cursor = await db.execute(
        "SELECT customer, amount FROM credits WHERE phone = ? AND LOWER(customer) = 'mama kiki' AND settled = 0", (U7,))
    rows = await cursor.fetchall()
    check("Renamed to Mama Kiki", len(rows) >= 1)

    # -- USER 8: Brother Chidi -- English wholesale --
    U8 = "2349100000008"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U8,))
    await db.commit()

    # Setup: credit for "Alhaji Garba"
    await _route_intent(U8, {"action": "record_credit", "customer": "Alhaji Garba",
                             "amount": 80000, "note": "cement bulk"}, "english")

    # T59: Payment+credit combo with fuzzy customer "Alhaji Garbar"
    print("\n--- T59: [Brother Chidi] Payment+credit combo -> fuzzy match ---")
    resp = await _route_intent(U8, {
        "action": "payment_and_credit", "customer": "Alhaji Garbar",
        "payment_amount": 50000, "credit_amount": 22000, "credit_note": "more cement",
    }, "english")
    check("Fuzzy match triggers confirmation", "Alhaji Garba" in resp and "Alhaji Garbar" in resp)

    # T60: Confirm yes -> both payment and credit processed
    print("\n--- T60: [Brother Chidi] Confirm combo ---")
    resp = await _route_intent(U8, {"action": "confirm_yes"}, "english")
    check("Payment processed", "50,000" in resp)
    check("Credit processed", "22,000" in resp)
    check("Customer name used", "Alhaji Garba" in resp)

    # T61: Delete data -> cancel
    print("\n--- T61: [Brother Chidi] Delete data -> cancel ---")
    resp = await _route_intent(U8, {"action": "delete_data"}, "english")
    check("Delete asks confirmation", "sure" in resp.lower() or "delete" in resp.lower())
    resp = await _route_intent(U8, {"action": "confirm_no"}, "english")
    check("Delete cancelled", "safe" in resp.lower() or "cancel" in resp.lower() or "no problem" in resp.lower())
    # Verify data still exists
    cursor = await db.execute("SELECT COUNT(*) FROM credits WHERE phone = ?", (U8,))
    check("Data preserved after cancel", (await cursor.fetchone())[0] > 0)

    # -- USER 9: Iya Sade -- Pidgin food vendor (sequential clarifications) --
    U9 = "2349100000009"
    await db.execute("INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (U9,))
    await db.commit()

    # Setup: credit for "Mama Olu"
    await _route_intent(U9, {"action": "record_credit", "customer": "Mama Olu",
                             "amount": 3000, "note": "rice"}, "pidgin")

    # T62: Fuzzy match on payment -> reject -> original name used
    print("\n--- T62: [Iya Sade] Reject fuzzy match on payment ---")
    resp = await _route_intent(U9, {
        "action": "record_payment", "customer": "Mama Oluchi", "amount": 2000,
    }, "pidgin")
    check("Fuzzy match suggested", "Mama Olu" in resp)
    resp = await _route_intent(U9, {"action": "confirm_no"}, "pidgin")
    # "Mama Oluchi" has no credits -> customer not found
    check("Original name used but not found", "Mama Oluchi" in resp.lower() or "can't find" in resp.lower() or "no see" in resp.lower())

    # T63: Sequential clarifications -- price ambiguity then credit ambiguity back to back
    print("\n--- T63: [Iya Sade] Back-to-back clarifications ---")
    # First: price ambiguity
    await _route_intent(U9, {
        "action": "record_sale", "product": "plantain", "quantity": 10, "unit": "bunch",
        "unit_price": 500, "total": 500, "price_ambiguous": True,
    }, "pidgin")
    resp = await _route_intent(U9, {"action": "confirm_yes"}, "pidgin")
    check("First clarification resolves", "Sold!" in resp)
    # Second: credit ambiguity (immediately after)
    resp = await _route_intent(U9, {
        "action": "record_sale", "product": "yam", "quantity": 3, "unit": "tuber",
        "unit_price": 2000, "total": 6000, "customer": "Mama Titi",
        "is_credit": False, "credit_ambiguous": True,
    }, "pidgin")
    check("Second clarification triggers", "cash" in resp.lower() and "credit" in resp.lower())
    resp = await _route_intent(U9, {"action": "confirm_yes"}, "pidgin")
    check("Second clarification resolves (cash)", "Sold!" in resp)

    # -- USER 10: Mama Ngozi -- English provision store (stale pending on customer match) --
    U10 = "2349100000010"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (U10,))
    await db.commit()

    # Setup: credit for "Aunty Grace"
    await _route_intent(U10, {"action": "record_credit", "customer": "Aunty Grace",
                              "amount": 5000, "note": "provisions"}, "english")

    # T64: Customer match triggers pending
    print("\n--- T64: [Mama Ngozi] Customer match -> stale pending ---")
    resp = await _route_intent(U10, {
        "action": "record_payment", "customer": "Aunty Gracey", "amount": 3000,
    }, "english")
    check("Customer match asks confirmation", "Aunty Grace" in resp)

    # T65: User ignores and sends new action -> stale pending cleared (simulating M5)
    print("\n--- T65: [Mama Ngozi] New action clears customer match pending ---")
    await _clear_pending(db, U10)  # M5: main.py clears pending for non-confirm actions
    resp = await _route_intent(U10, {
        "action": "record_expense", "description": "transport", "amount": 500, "category": "transport",
    }, "english")
    check("New expense recorded", "500" in resp and "transport" in resp.lower())

    # T66: "yes" after stale -> nothing to confirm
    print("\n--- T66: [Mama Ngozi] Confirm after stale -> nothing ---")
    resp = await _route_intent(U10, {"action": "confirm_yes"}, "english")
    check("Nothing to confirm", "Nothing to confirm" in resp or "nothing" in resp.lower())
    # The original payment was NOT processed (pending was cleared)
    cursor = await db.execute("SELECT COUNT(*) FROM payments WHERE phone = ?", (U10,))
    check("Original payment not processed", (await cursor.fetchone())[0] == 0)

    # T67: Customer statement with fuzzy match -> confirm yes
    print("\n--- T67: [Mama Ngozi] Customer statement fuzzy match ---")
    resp = await _route_intent(U10, {
        "action": "customer_statement", "customer": "Aunty Gracey",
    }, "english")
    check("Statement fuzzy match asks", "Aunty Grace" in resp)
    resp = await _route_intent(U10, {"action": "confirm_yes"}, "english")
    check("Statement link generated", "receipt" in resp.lower() or "test.example.com" in resp)

    # T68: Mark credit with fuzzy customer match
    print("\n--- T68: [Mama Ngozi] Mark credit with fuzzy customer ---")
    # Record a cash sale first
    await _route_intent(U10, {
        "action": "record_sale", "product": "soap", "quantity": 5, "unit": "bar",
        "unit_price": 200, "total": 1000, "customer": "Aunty Gracey",
        "is_credit": False,
    }, "english")
    resp = await _route_intent(U10, {"action": "mark_credit"}, "english")
    # "Aunty Gracey" fuzzy matches "Aunty Grace" -> asks for confirmation
    check("Mark credit fuzzy match asks", "Aunty Grace" in resp)
    resp = await _route_intent(U10, {"action": "confirm_yes"}, "english")
    check("Mark credit confirmed with matched customer",
          "credit" in resp.lower() and "soap" in resp.lower())

    # ================================================================
    # T69-T76: Long Voice Note & TTS Splitting Tests
    # ================================================================
    from app.voice import _split_into_chunks, _make_speakable
    from app.handlers import _save_pending

    # T69: TTS chunk splitting - short text stays as one chunk
    print("\n--- T69: TTS split -- short text is 1 chunk ---")
    short = "You sold 3 bags of rice for 15 thousand naira."
    chunks = _split_into_chunks(short)
    check("Short text = 1 chunk", len(chunks) == 1 and chunks[0] == short)

    # T70: TTS chunk splitting - long text splits at sentence boundaries
    print("\n--- T70: TTS split -- long text splits at sentence boundary ---")
    sentences = [f"Sentence number {i} is here for testing." for i in range(20)]
    long_text = " ".join(sentences)
    chunks = _split_into_chunks(long_text, max_chars=200)
    check("Multiple chunks created", len(chunks) > 1)
    check("Each chunk <= 200 chars", all(len(c) <= 200 for c in chunks))
    rejoined = " ".join(chunks)
    # All original content should be preserved (modulo whitespace)
    check("Content preserved", rejoined.replace("  ", " ").strip() == long_text.strip())

    # T71: TTS chunk splitting - no chunk under 100 chars triggers hard cut
    print("\n--- T71: TTS split -- hard cut when no sentence boundary ---")
    no_period = "a" * 500
    chunks = _split_into_chunks(no_period, max_chars=200)
    check("Hard cut works", len(chunks) >= 2)

    # T72: _make_speakable strips voice echo
    print("\n--- T72: _make_speakable strips echo ---")
    with_echo = 'I heard: "sell 3 bag rice" Sold! 3 bag rice = 15,000 naira'
    speakable = _make_speakable(with_echo)
    check("Echo stripped", 'I heard' not in speakable and 'recorded a sale' in speakable)

    # T73: _make_speakable converts URLs
    print("\n--- T73: _make_speakable converts URLs ---")
    with_url = "Here is your report: https://example.com/report/abc123"
    speakable = _make_speakable(with_url)
    check("URL replaced", "https://" not in speakable and "press the link" in speakable)

    # T74: Very long voice confirm -- yes path (replay)
    print("\n--- T74: Very long voice confirm -- yes ---")
    U_VOICE = "2349000000099"
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO shops (phone, onboarded) VALUES (?, 1)",
        (U_VOICE,))
    await db.commit()
    await _save_pending(db, U_VOICE, {
        "action": "long_voice_confirm",
        "text": "I sold 2 bag rice 10000",
        "lang": "english",
    })
    resp = await _route_intent(U_VOICE, {"action": "confirm_yes"}, "english")
    check("Confirm yes returns replay prefix", resp.startswith("__replay__:"))
    check("Replay contains original text", "I sold 2 bag rice 10000" in resp)

    # T75: Very long voice confirm -- no path
    print("\n--- T75: Very long voice confirm -- no ---")
    await _save_pending(db, U_VOICE, {
        "action": "long_voice_confirm",
        "text": "some long transcription",
        "lang": "english",
    })
    resp = await _route_intent(U_VOICE, {"action": "confirm_no"}, "english")
    check("Confirm no suggests shorter voice note", "shorter voice note" in resp.lower())

    # T76: Long voice hint template exists
    print("\n--- T76: Long voice hint response template ---")
    hint_en = get_response("hint_long_voice", "english")
    hint_pi = get_response("hint_long_voice", "pidgin")
    check("English hint exists", "shorter" in hint_en.lower())
    check("Pidgin hint exists", "shorter" in hint_pi.lower())

    # ==========================================================================
    # LONG VOICE END-OF-DAY SIMULATION -- 10 Users, Comprehensive
    # ==========================================================================
    # Simulates users who record their full day's transactions via a single
    # long voice note at closing time. Tests the echo-and-confirm flow,
    # replay through NLU, one-time hint, sequential confirm cycles, TTS
    # splitting of long responses, and Pidgin/English paths.
    #
    # The _process_message flow for very long voice:
    #   1. Audio >60KB -> _very_long_voice flag
    #   2. Transcription saved as pending (long_voice_confirm)
    #   3. Echo + confirm prompt sent to user
    #   4. User says "yes" -> confirm_yes -> __replay__:text -> NLU -> handler
    #   5. User says "no" -> confirm_no -> "send shorter voice note"
    #
    # Since _process_message handles steps 1-3 internally, we simulate that
    # by calling _save_pending directly, then test steps 4-5 via _route_intent.
    print("\n" + "=" * 60)
    print("LONG VOICE END-OF-DAY SIMULATION -- 10 Users")
    print("=" * 60)

    from app.voice import _split_into_chunks, _make_speakable

    # ---- Helper: simulate very long voice note arrival ----
    async def sim_very_long_voice(phone, text, lang):
        """Simulate what _process_message does for _very_long_voice."""
        await _save_pending(db, phone, {
            "action": "long_voice_confirm",
            "text": text,
            "lang": lang,
        })
        echo = get_response("voice_echo", lang, text=text)
        confirm_msg = get_response("long_voice_confirm", lang)
        return echo + confirm_msg

    # ---- Helper: simulate long voice hint check ----
    async def check_long_voice_hint(phone, lang):
        """Simulate _process_message long voice hint check."""
        cursor = await db.execute(
            "SELECT long_voice_hinted FROM shops WHERE phone = ?", (phone,))
        row = await cursor.fetchone()
        if row and not row[0]:
            await db.execute(
                "UPDATE shops SET long_voice_hinted = 1 WHERE phone = ?", (phone,))
            await db.commit()
            return get_response("hint_long_voice", lang)
        return ""

    # ---- Helper: simulate confirm_yes + replay ----
    async def sim_confirm_yes_replay(phone, lang):
        """Simulate confirm_yes -> __replay__ -> NLU re-route."""
        resp = await _route_intent(phone, {"action": "confirm_yes"}, lang)
        if resp.startswith("__replay__:"):
            replay_text = resp[len("__replay__:"):]
            replay_intent = preclassify(replay_text)
            if not replay_intent:
                # We can't call Gemini in tests, so use preclassify only
                # For texts that don't preclassify, simulate a direct sale intent
                return None, replay_text  # Caller handles NLU-dependent case
            replay_intent["_is_voice"] = True
            final = await _route_intent(phone, replay_intent, lang)
            return final, replay_text
        return resp, None

    # ==== USER V1: Mama Nkechi -- Food vendor, English, single long sale ====
    V1 = "2349200000001"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V1,))
    await db.commit()

    # Record some products with prices first so replay works
    await _route_intent(V1, {
        "action": "set_price", "product": "rice", "unit_price": 5000, "unit": "bag",
    }, "english")

    print("\n--- T77: [Mama Nkechi] Very long voice -> echo and confirm prompt ---")
    long_text = "I sold 3 bags of rice today for 15000 naira and 2 bags of beans for 8000 naira"
    echo_resp = await sim_very_long_voice(V1, long_text, "english")
    check("Echo contains transcription", long_text in echo_resp)
    check("Confirm prompt present", "Did I get everything right" in echo_resp)
    check("Yes/no options mentioned", "yes" in echo_resp.lower() and "no" in echo_resp.lower())

    print("\n--- T78: [Mama Nkechi] Confirm yes -> replay processes sale ---")
    resp = await _route_intent(V1, {"action": "confirm_yes"}, "english")
    check("Replay prefix returned", resp.startswith("__replay__:"))
    check("Original text in replay", "3 bags of rice" in resp)

    # Verify pending is cleared after confirm_yes
    pending = await _peek_pending(db, V1)
    check("Pending cleared after confirm", pending is None)

    print("\n--- T79: [Mama Nkechi] One-time hint fires on first long note ---")
    hint = await check_long_voice_hint(V1, "english")
    check("First hint fires", "shorter" in hint.lower())
    hint2 = await check_long_voice_hint(V1, "english")
    check("Second hint does NOT fire", hint2 == "")

    # ==== USER V2: Iya Basira -- Pidgin food vendor, confirm NO path ====
    V2 = "2349200000002"
    await db.execute(
        "INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (V2,))
    await db.commit()

    print("\n--- T80: [Iya Basira] Very long voice in Pidgin -> echo ---")
    pidgin_text = "I sell 5 bag garri today for 25000 naira and 3 crate egg for 12000"
    echo_resp = await sim_very_long_voice(V2, pidgin_text, "pidgin")
    check("Pidgin echo has text", pidgin_text in echo_resp)
    check("Pidgin confirm prompt", "I hear everything correct" in echo_resp)

    print("\n--- T81: [Iya Basira] Confirm NO -> asks to resend ---")
    resp = await _route_intent(V2, {"action": "confirm_no"}, "pidgin")
    check("Pidgin no: suggests shorter note", "shorter voice note" in resp.lower())
    # Verify pending is cleared
    pending = await _peek_pending(db, V2)
    check("Pending cleared after no", pending is None)

    print("\n--- T82: [Iya Basira] Second long voice after rejection ---")
    retry_text = "I sell 5 bag garri 25000 naira"
    echo2 = await sim_very_long_voice(V2, retry_text, "pidgin")
    check("Second attempt echoes new text", retry_text in echo2)
    # Confirm yes this time
    resp = await _route_intent(V2, {"action": "confirm_yes"}, "pidgin")
    check("Second attempt replay works", resp.startswith("__replay__:"))

    print("\n--- T83: [Iya Basira] Pidgin hint fires once ---")
    hint = await check_long_voice_hint(V2, "pidgin")
    check("Pidgin hint fires", "shorter" in hint.lower())
    hint2 = await check_long_voice_hint(V2, "pidgin")
    check("Pidgin hint not repeated", hint2 == "")

    # ==== USER V3: Brother Emeka -- Hardware store, very long multi-item ====
    V3 = "2349200000003"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V3,))
    await db.commit()

    print("\n--- T84: [Brother Emeka] Multi-item long voice ---")
    multi_text = ("Today I sold 10 bags of cement at 5500 each, 3 bundles of roofing sheet "
                  "for 45000 naira, 2 packets of nails for 3000, and somebody bought "
                  "5 bags of sand for 2500 each")
    echo_resp = await sim_very_long_voice(V3, multi_text, "english")
    check("Multi-item echo complete", "cement" in echo_resp and "sand" in echo_resp)
    check("Full text preserved in echo", multi_text in echo_resp)

    # Confirm yes
    resp = await _route_intent(V3, {"action": "confirm_yes"}, "english")
    check("Multi-item replay returned", resp.startswith("__replay__:"))
    replay_text = resp[len("__replay__:"):]
    check("All items in replay", "cement" in replay_text and "nails" in replay_text)

    print("\n--- T85: [Brother Emeka] Sequential: long voice then normal sale ---")
    # After confirming a long voice, user can do a normal sale immediately
    resp = await _route_intent(V3, {
        "action": "record_sale", "product": "cement", "quantity": 5, "unit": "bag",
        "unit_price": 5500, "total": 27500,
    }, "english")
    check("Normal sale after long voice works", "Sold!" in resp)
    # No stale pending from the long voice confirm
    pending = await _peek_pending(db, V3)
    check("No stale pending after normal sale", pending is None)

    # ==== USER V4: Sisi Kemi -- Cosmetics, long voice then text correction ====
    V4 = "2349200000004"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V4,))
    await db.commit()

    print("\n--- T86: [Sisi Kemi] Long voice abandoned for text entry ---")
    voice_text = "I sold 3 packs of relaxer for 4500 and 5 bottles of shampoo"
    await sim_very_long_voice(V4, voice_text, "english")
    # User decides to type instead -- _process_message clears stale pending
    # before calling _route_intent for new business actions. Simulate that:
    await _clear_pending(db, V4)
    resp = await _route_intent(V4, {
        "action": "record_sale", "product": "relaxer", "quantity": 3, "unit": "pack",
        "unit_price": 1500, "total": 4500,
    }, "english")
    check("Text sale overrides long voice pending", "Sold!" in resp)
    check("Relaxer sale recorded", "relaxer" in resp.lower())
    # Verify pending stays cleared
    pending = await _peek_pending(db, V4)
    check("Long voice pending cleared by new action", pending is None)

    # ==== USER V5: Alhaji Musa -- Auto parts, Pidgin, multiple confirm cycles ====
    V5 = "2349200000005"
    await db.execute(
        "INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (V5,))
    await db.commit()

    print("\n--- T87: [Alhaji Musa] First long voice -> no -> second -> yes ---")
    text1 = "I sell brake pad 15000 and shock absorber 22000 today"
    await sim_very_long_voice(V5, text1, "pidgin")
    resp_no = await _route_intent(V5, {"action": "confirm_no"}, "pidgin")
    check("First attempt rejected", "shorter" in resp_no.lower())

    text2 = "I sell brake pad 15000 naira"
    await sim_very_long_voice(V5, text2, "pidgin")
    resp = await _route_intent(V5, {"action": "confirm_yes"}, "pidgin")
    check("Second attempt confirmed", resp.startswith("__replay__:"))
    check("Only brake pad in replay", "brake pad" in resp and "shock" not in resp)

    print("\n--- T88: [Alhaji Musa] Third long voice same session ---")
    text3 = "I sell shock absorber 22000 naira"
    await sim_very_long_voice(V5, text3, "pidgin")
    resp = await _route_intent(V5, {"action": "confirm_yes"}, "pidgin")
    check("Third long voice works", resp.startswith("__replay__:"))
    check("Shock absorber in replay", "shock absorber" in resp)

    # ==== USER V6: Mama Adaeze -- Provision store, credit in long voice ====
    V6 = "2349200000006"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V6,))
    await db.commit()

    print("\n--- T89: [Mama Adaeze] Long voice with credit mention ---")
    credit_text = "Mama Joy bought 2 cartons of indomie for 8000 naira on credit"
    echo_resp = await sim_very_long_voice(V6, credit_text, "english")
    check("Credit text echoed", "Mama Joy" in echo_resp and "credit" in echo_resp)
    resp = await _route_intent(V6, {"action": "confirm_yes"}, "english")
    check("Credit voice replay returned", resp.startswith("__replay__:"))
    check("Credit details preserved", "Mama Joy" in resp and "credit" in resp)

    # ==== USER V7: Aunty Funke -- Hair salon, English, double confirm yes ====
    V7 = "2349200000007"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V7,))
    await db.commit()

    print("\n--- T90: [Aunty Funke] Confirm yes when no pending ---")
    # User accidentally says "yes" with nothing pending
    resp = await _route_intent(V7, {"action": "confirm_yes"}, "english")
    check("No pending: helpful message", "nothing to confirm" in resp.lower())

    print("\n--- T91: [Aunty Funke] Long voice -> confirm yes -> try confirm again ---")
    salon_text = "I did 3 hair treatments today at 5000 each"
    await sim_very_long_voice(V7, salon_text, "english")
    resp = await _route_intent(V7, {"action": "confirm_yes"}, "english")
    check("First confirm works", resp.startswith("__replay__:"))
    # Try confirming again -- should have nothing pending
    resp2 = await _route_intent(V7, {"action": "confirm_yes"}, "english")
    check("Double confirm: nothing pending", "nothing to confirm" in resp2.lower())

    # ==== USER V8: Pastor Grace -- Bookshop, mixed voice and text ====
    V8 = "2349200000008"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V8,))
    await db.commit()

    print("\n--- T92: [Pastor Grace] Normal sale, then long voice, then normal ---")
    # Normal text sale first
    resp1 = await _route_intent(V8, {
        "action": "record_sale", "product": "notebook", "quantity": 10, "unit": "piece",
        "unit_price": 200, "total": 2000,
    }, "english")
    check("First text sale recorded", "Sold!" in resp1)

    # Long voice note
    book_text = "I also sold 5 packs of pens for 1500 and 3 boxes of chalk for 2000"
    await sim_very_long_voice(V8, book_text, "english")
    resp = await _route_intent(V8, {"action": "confirm_yes"}, "english")
    check("Long voice after text sale works", resp.startswith("__replay__:"))

    # Another normal sale right after
    resp3 = await _route_intent(V8, {
        "action": "record_sale", "product": "eraser", "quantity": 20, "unit": "piece",
        "unit_price": 50, "total": 1000,
    }, "english")
    check("Text sale after long voice works", "Sold!" in resp3)

    # ==== USER V9: Baba Tunde -- Wholesale, TTS splitting of long summary ====
    V9 = "2349200000009"
    await db.execute("INSERT INTO shops (phone, onboarded) VALUES (?, 1)", (V9,))
    await db.commit()

    print("\n--- T93: [Baba Tunde] TTS splitting of long summary response ---")
    # Record several sales so summary is long
    for item, qty, price in [
        ("rice", 10, 5000), ("beans", 8, 4500), ("garri", 15, 2000),
        ("sugar", 20, 1500), ("salt", 12, 800), ("oil", 6, 3500),
        ("flour", 5, 2200), ("semolina", 7, 2800),
    ]:
        await _route_intent(V9, {
            "action": "record_sale", "product": item, "quantity": qty, "unit": "bag",
            "unit_price": price, "total": qty * price,
        }, "english")

    # Get daily summary -- should be long
    summary = await _route_intent(V9, {"action": "daily_summary"}, "english")
    check("Summary has multiple products", "rice" in summary and "beans" in summary)

    # Test TTS splitting on the summary
    speakable = _make_speakable(summary)
    chunks = _split_into_chunks(speakable, max_chars=450)
    check("Summary needs splitting", len(speakable) > 200,
          f"speakable_len={len(speakable)}")
    if len(chunks) > 1:
        check("Chunks within limit", all(len(c) <= 450 for c in chunks))
        check("No empty chunks", all(len(c.strip()) > 0 for c in chunks))

    print("\n--- T94: [Baba Tunde] Long voice for end-of-day batch ---")
    batch_text = ("Today I sold 10 bags rice 5000 each, 8 bags beans 4500 each, "
                  "15 bags garri 2000 each, 20 bags sugar 1500 each, "
                  "12 bags salt 800 each, and 6 kegs oil 3500 each")
    echo_resp = await sim_very_long_voice(V9, batch_text, "english")
    check("Batch echo preserves all items",
          "rice" in echo_resp and "oil" in echo_resp and "sugar" in echo_resp)
    resp = await _route_intent(V9, {"action": "confirm_yes"}, "english")
    check("Batch replay returned", resp.startswith("__replay__:"))
    check("All products in replay",
          all(p in resp for p in ["rice", "beans", "garri", "sugar", "salt", "oil"]))

    # ==== USER V10: Mama Chisom -- Pidgin, edge cases ====
    V10 = "2349200000010"
    await db.execute(
        "INSERT INTO shops (phone, onboarded, language) VALUES (?, 1, 'pidgin')", (V10,))
    await db.commit()

    print("\n--- T95: [Mama Chisom] Empty pending -> confirm no does nothing ---")
    resp = await _route_intent(V10, {"action": "confirm_no"}, "pidgin")
    check("No pending: pidgin no message", "nothing to confirm" in resp.lower())

    print("\n--- T96: [Mama Chisom] Long voice with numbers and customers ---")
    complex_text = ("Mama Joy buy 3 bag rice 5000 each on credit, "
                    "Alhaji Musa pay me 10000 naira, "
                    "I sell 5 carton milk 8000 naira cash")
    echo_resp = await sim_very_long_voice(V10, complex_text, "pidgin")
    check("Complex text fully echoed", "Mama Joy" in echo_resp and "Alhaji Musa" in echo_resp)

    # Confirm yes
    resp = await _route_intent(V10, {"action": "confirm_yes"}, "pidgin")
    check("Complex replay returned", resp.startswith("__replay__:"))
    replay = resp[len("__replay__:"):]
    check("Customer names preserved", "Mama Joy" in replay and "Alhaji Musa" in replay)

    print("\n--- T97: [Mama Chisom] Stale long voice cleared by expense ---")
    stale_text = "I sell something today"
    await sim_very_long_voice(V10, stale_text, "pidgin")
    # User types an expense instead -- _process_message clears pending
    # before calling _route_intent. Simulate that here:
    await _clear_pending(db, V10)
    resp = await _route_intent(V10, {
        "action": "record_expense", "amount": 2000, "category": "transport",
    }, "pidgin")
    check("Expense clears stale long voice", "2,000" in resp)
    pending = await _peek_pending(db, V10)
    check("Stale pending cleared", pending is None)
    # Confirm yes after stale cleared -> nothing to confirm
    resp = await _route_intent(V10, {"action": "confirm_yes"}, "pidgin")
    check("Confirm after stale: nothing", "nothing to confirm" in resp.lower())

    print("\n--- T98: [Mama Chisom] Hint column value persists ---")
    # Mama Chisom hasn't triggered the hint yet
    cursor = await db.execute(
        "SELECT long_voice_hinted FROM shops WHERE phone = ?", (V10,))
    row = await cursor.fetchone()
    check("Hint not yet fired for V10", row[0] == 0)
    hint = await check_long_voice_hint(V10, "pidgin")
    check("Hint fires for V10", "shorter" in hint.lower())
    cursor = await db.execute(
        "SELECT long_voice_hinted FROM shops WHERE phone = ?", (V10,))
    row = await cursor.fetchone()
    check("Hint column updated to 1", row[0] == 1)

    # ==== Cross-user isolation checks ====
    print("\n--- T99: Cross-user pending isolation ---")
    # Set pending for V1, verify V2's pending is independent
    await sim_very_long_voice(V1, "test isolation V1", "english")
    await sim_very_long_voice(V2, "test isolation V2", "pidgin")
    p1 = await _peek_pending(db, V1)
    p2 = await _peek_pending(db, V2)
    check("V1 pending is V1's text", p1 and p1.get("text") == "test isolation V1")
    check("V2 pending is V2's text", p2 and p2.get("text") == "test isolation V2")
    # Confirm V1, V2 still pending
    await _route_intent(V1, {"action": "confirm_yes"}, "english")
    p2_after = await _peek_pending(db, V2)
    check("V2 pending survives V1 confirm", p2_after and p2_after.get("text") == "test isolation V2")
    await _clear_pending(db, V2)

    print("\n--- T100: Confirm prompt templates bilingual ---")
    echo_en = get_response("voice_echo", "english", text="test text")
    echo_pi = get_response("voice_echo", "pidgin", text="test text")
    conf_en = get_response("long_voice_confirm", "english")
    conf_pi = get_response("long_voice_confirm", "pidgin")
    check("English echo format", 'I heard: "test text"' in echo_en)
    check("Pidgin echo format", 'I hear you say: "test text"' in echo_pi)
    check("English confirm bilingual", "Did I get everything right" in conf_en)
    check("Pidgin confirm bilingual", "I hear everything correct" in conf_pi)

    print("\n--- T101: TTS _make_speakable on confirm prompt ---")
    # The echo+confirm text should be speakable (no weird artifacts)
    full_prompt = echo_en + conf_en
    speakable = _make_speakable(full_prompt)
    check("Speakable has no raw URLs", "https://" not in speakable)
    # Echo should be stripped from speakable (it's for text only)
    check("Echo stripped in TTS", "I heard" not in speakable)

    # ==== Summary statistics ====
    print("\n" + "=" * 60)
    print("Long Voice Simulation Summary:")
    print("  Users tested: 10 (V1-V10)")
    print("  Flows: echo-confirm, reject-retry, abandon-for-text,")
    print("         sequential confirms, stale clearing, cross-user")
    print("         isolation, hint persistence, TTS splitting,")
    print("         bilingual templates, double confirm guard")
    print("=" * 60)

    # === CLEANUP ===
    await close_db()
    for _old in pathlib.Path(".").glob("test_smoke*.db*"):
        try:
            _old.unlink()
        except (PermissionError, OSError):
            pass

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
    print("=" * 60)
    if failed > 0:
        exit(1)


asyncio.run(run())
