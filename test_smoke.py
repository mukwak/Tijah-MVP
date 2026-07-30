"""End-to-end smoke test for Tijah MVP. Run: python test_smoke.py"""
import asyncio
import os
import pathlib

# Force local SQLite for testing
os.environ["DATABASE_URL"] = ""
os.environ["DB_PATH"] = "test_smoke.db"
os.environ["BASE_URL"] = "https://test.example.com"

# Clean up from any prior run
pathlib.Path("test_smoke.db").unlink(missing_ok=True)

# Must import AFTER env is set
from app.database import get_db, close_db
from app.preclassifier import preclassify
from app.main import _route_intent
from app.responses import get_response

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

    # User re-sends with correct name and same amount — should rename, not duplicate
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
    # Confirm yes — should delete
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

    # === CLEANUP ===
    await close_db()
    pathlib.Path("test_smoke.db").unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
    print("=" * 60)
    if failed > 0:
        exit(1)


asyncio.run(run())
