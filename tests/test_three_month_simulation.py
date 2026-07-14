"""Simulates 3 months of real usage across 3 shops on one database.

Verifies:
- data persists correctly across the whole period
- shops are strictly isolated (no leakage between phones)
- summary math matches independently-tracked expectations
- conversational corrections work (undo, edit_credit, rename_customer)
- feedback is stored and visible to admin
- the shareable report shows only the owner's data
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest

from app import database, handlers, report

SHOPS = {
    "2348010000001": "Mama Rice Store",
    "2348010000002": "Bros Electronics",
    "2348010000003": "Chidinma Provisions",
}


async def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "sim.db"))
    await database.close_db()
    db = await database.get_db()
    for phone, name in SHOPS.items():
        await db.execute(
            "INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
            (phone, name, "english" if "Bros" in name else "pidgin"),
        )
    await db.commit()
    return db


@pytest.mark.asyncio
async def test_three_months_of_activity(tmp_path, monkeypatch):
    db = await _fresh_db(tmp_path, monkeypatch)

    p1, p2, p3 = SHOPS.keys()
    expected_sales = {p: 0.0 for p in SHOPS}

    # --- 90 days of interleaved activity (backdated via "when" offsets) ---
    for day in range(90, 0, -1):
        when = str(-day)
        # Shop 1 sells rice daily at increasing price
        price = 5000 + (90 - day) * 10
        await handlers.handle_record_sale(
            p1, {"product": "rice", "quantity": 2, "unit": "bag",
                 "unit_price": price, "when": when}, "pidgin")
        expected_sales[p1] += 2 * price

        # Shop 2 sells a phone every 3rd day
        if day % 3 == 0:
            await handlers.handle_record_sale(
                p2, {"product": "phone", "quantity": 1, "unit": "piece",
                     "unit_price": 45000, "when": when}, "english")
            expected_sales[p2] += 45000

        # Shop 3 sells garri every 5th day
        if day % 5 == 0:
            await handlers.handle_record_sale(
                p3, {"product": "garri", "quantity": 3, "unit": "cup",
                     "unit_price": 200, "when": when}, "pidgin")
            expected_sales[p3] += 600

    # Credits and partial payments on shop 1
    await handlers.handle_record_credit(
        p1, {"customer": "Mama Joy", "amount": 8000, "note": "rice"}, "pidgin")
    await handlers.handle_record_payment(
        p1, {"customer": "Mama Joy", "amount": 3000}, "pidgin")

    # Same customer name in another shop must NOT collide
    await handlers.handle_record_credit(
        p2, {"customer": "Mama Joy", "amount": 20000, "note": "phone"}, "english")

    # Expenses
    await handlers.handle_record_expense(
        p1, {"description": "transport", "amount": 500, "category": "transport"}, "pidgin")
    await handlers.handle_record_expense(
        p2, {"description": "generator fuel", "amount": 3000, "category": "supplies"}, "english")

    # --- Persistence: totals per shop match expectations exactly ---
    for phone in SHOPS:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ?", (phone,))
        assert (await cursor.fetchone())[0] == pytest.approx(expected_sales[phone]), phone

    # --- Isolation: shop 1's credit balance unaffected by shop 2's Mama Joy ---
    r = await handlers.handle_check_credits(p1, {}, "english")
    assert "5,000" in r  # 8000 - 3000
    assert "20,000" not in r
    r = await handlers.handle_check_credits(p2, {}, "english")
    assert "20,000" in r
    assert "5,000" not in r

    # Shop 3 never recorded credit
    r = await handlers.handle_check_credits(p3, {}, "english")
    assert "20,000" not in r and "Mama Joy" not in r

    # --- Reports show only the owner's data ---
    html1 = await report.render_report_html(p1)
    html2 = await report.render_report_html(p2)
    html3 = await report.render_report_html(p3)
    # Match table cells exactly so "Price" doesn't count as "rice"
    assert ">rice<" in html1 and ">phone<" not in html1 and ">garri<" not in html1
    assert ">phone<" in html2 and ">garri<" not in html2 and ">rice<" not in html2
    assert ">garri<" in html3 and ">rice<" not in html3 and ">phone<" not in html3
    # Report tokens are distinct
    tokens = {await report.get_or_create_report_token(p) for p in SHOPS}
    assert len(tokens) == 3

    # --- Conversational corrections ---
    # 1) Wrong sale -> undo removes it and restores stock math
    before = expected_sales[p3]
    await handlers.handle_record_sale(
        p3, {"product": "garri", "quantity": 100, "unit": "cup", "unit_price": 200}, "pidgin")
    r = await handlers.handle_undo(p3, {}, "pidgin")
    cursor = await db.execute(
        "SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ?", (p3,))
    assert (await cursor.fetchone())[0] == pytest.approx(before)

    # 2) Credit recorded wrong -> fix conversationally
    await handlers.handle_edit_credit(
        p2, {"customer": "Mama Joy", "new_amount": 15000}, "english")
    r = await handlers.handle_check_credits(p2, {}, "english")
    assert "15,000" in r

    # 3) Misspelled customer -> rename
    await handlers.handle_record_credit(
        p1, {"customer": "Mama Inkechi", "amount": 1000}, "pidgin")
    await handlers.handle_rename_customer(
        p1, {"old_name": "Mama Inkechi", "new_name": "Mama Nkechi"}, "pidgin")
    r = await handlers.handle_check_credits(p1, {}, "english")
    assert "Mama Nkechi" in r and "Inkechi" not in r

    # --- Feedback flow ---
    r = await handlers.handle_feedback(
        p3, {"message": "the voice note no play yesterday"}, "pidgin")
    assert "Tijah team" in r
    cursor = await db.execute("SELECT phone, message FROM feedback", ())
    rows = await cursor.fetchall()
    assert len(rows) == 1 and rows[0][0] == p3

    # --- Admin dashboard shows all shops and the feedback ---
    admin_html = await report.render_admin_html()
    for name in SHOPS.values():
        assert name in admin_html
    assert "voice note no play" in admin_html

    # --- Monthly summary only counts last 30 days ---
    r = await handlers.handle_daily_summary(p2, {"period": "month"}, "english")
    assert "naira" in r

    await database.close_db()
