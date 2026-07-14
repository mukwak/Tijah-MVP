"""Nudges must be the natural next step after each action.

- Sale of an untracked product -> offer stock tracking, no confusing oversold warning
- Sale of a tracked product -> normal stock warnings apply
- Stock added without a selling price -> ask for the price
- Only one nudge per response, and nudges stop after the first few times
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest

from app import database, handlers

PHONE = "2348099990001"


async def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "nudge.db"))
    await database.close_db()
    db = await database.get_db()
    await db.execute(
        "INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
        (PHONE, "Nudge Shop", "english"),
    )
    await db.commit()
    return db


@pytest.mark.asyncio
async def test_sale_of_untracked_product_offers_stock_tracking(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)

    r = await handlers.handle_record_sale(
        PHONE, {"product": "indomie", "quantity": 5, "unit": "carton", "unit_price": 7000}, "english")
    # Offers to track stock for this product
    assert "how many indomie you have" in r
    # No confusing oversold/finished warnings for untracked products
    assert "short by" not in r and "finished" not in r
    # Only one nudge
    assert "owes you money" not in r

    # Nudge stops after the first couple of sales
    await handlers.handle_record_sale(
        PHONE, {"product": "indomie", "quantity": 2, "unit": "carton", "unit_price": 7000}, "english")
    r = await handlers.handle_record_sale(
        PHONE, {"product": "indomie", "quantity": 1, "unit": "carton", "unit_price": 7000}, "english")
    assert "how many indomie" not in r

    await database.close_db()


@pytest.mark.asyncio
async def test_sale_of_tracked_product_keeps_stock_warnings(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)

    await handlers.handle_add_stock(
        PHONE, {"product": "rice", "quantity": 3, "unit": "bag", "cost_price": 3000}, "english")
    r = await handlers.handle_record_sale(
        PHONE, {"product": "rice", "quantity": 5, "unit": "bag", "unit_price": 5000}, "english")
    # Tracked product -> oversell warning shows, no stock-tracking offer
    assert "short by" in r
    assert "how many rice" not in r

    await database.close_db()


@pytest.mark.asyncio
async def test_stock_without_price_asks_for_price(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)

    r = await handlers.handle_add_stock(
        PHONE, {"product": "garri", "quantity": 10, "unit": "bag", "cost_price": 2000}, "english")
    assert "What price do you sell garri" in r

    # Once a price is set, the price nudge goes away
    await handlers.handle_set_price(
        PHONE, {"product": "garri", "unit": "bag", "sell_price": 3000}, "english")
    r = await handlers.handle_add_stock(
        PHONE, {"product": "garri", "quantity": 5, "unit": "bag", "cost_price": 2000}, "english")
    assert "What price" not in r

    await database.close_db()


@pytest.mark.asyncio
async def test_expense_nudges_toward_summary(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)

    r = await handlers.handle_record_expense(
        PHONE, {"description": "transport", "amount": 500, "category": "transport"}, "english")
    assert "how did my shop do today" in r

    await database.close_db()


@pytest.mark.asyncio
async def test_sale_hints_rotate_for_discovery(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)
    # Track stock so we take the tracked-product hint path
    await handlers.handle_add_stock(
        PHONE, {"product": "rice", "quantity": 50, "unit": "bag", "cost_price": 3000}, "english")

    sale = {"product": "rice", "quantity": 1, "unit": "bag", "unit_price": 5000}
    r1 = await handlers.handle_record_sale(PHONE, dict(sale), "english")
    r2 = await handlers.handle_record_sale(PHONE, dict(sale), "english")
    r3 = await handlers.handle_record_sale(PHONE, dict(sale), "english")
    r4 = await handlers.handle_record_sale(PHONE, dict(sale), "english")
    assert "owes you money" in r1        # credit book
    assert "cancel that" in r2           # undo
    assert "how did my shop do" in r3    # summary
    for hint in ("owes you money", "cancel that", "how did my shop do"):
        assert hint not in r4            # hints stop after discovery

    await database.close_db()


@pytest.mark.asyncio
async def test_shop_name_asked_and_shows_on_report(tmp_path, monkeypatch):
    db = await _fresh_db(tmp_path, monkeypatch)
    await db.execute("UPDATE shops SET name = NULL WHERE phone = ?", (PHONE,))
    await db.commit()

    # No name yet -> report reply asks for it
    r = await handlers.handle_get_report(PHONE, {}, "english")
    assert "What is your shop's name" in r

    # Set it conversationally
    r = await handlers.handle_set_shop_name(PHONE, {"name": "Mama T Store"}, "english")
    assert "Mama T Store" in r

    # Shows at top of the report; no longer asked
    from app import report
    html_out = await report.render_report_html(PHONE)
    assert "<h1>Mama T Store</h1>" in html_out
    r = await handlers.handle_get_report(PHONE, {}, "english")
    assert "What is your shop's name" not in r

    await database.close_db()


@pytest.mark.asyncio
async def test_credits_list_offers_reminder(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)
    await handlers.handle_record_credit(
        PHONE, {"customer": "Mama Joy", "amount": 8000}, "english")

    r = await handlers.handle_check_credits(PHONE, {}, "english")
    assert 'say "remind Mama Joy"' in r

    await database.close_db()


@pytest.mark.asyncio
async def test_summary_insight_compares_with_yesterday(tmp_path, monkeypatch):
    await _fresh_db(tmp_path, monkeypatch)

    await handlers.handle_record_sale(
        PHONE, {"product": "rice", "quantity": 1, "unit": "bag",
                "unit_price": 5000, "when": "yesterday"}, "english")
    await handlers.handle_record_sale(
        PHONE, {"product": "rice", "quantity": 2, "unit": "bag", "unit_price": 5000}, "english")

    r = await handlers.handle_daily_summary(PHONE, {"period": "today"}, "english")
    assert "better than Yesterday" in r and "5,000" in r
    # Never opened the report -> pointed to it
    assert '"my report"' in r

    # Once they get their report link, the report hint stops
    await handlers.handle_get_report(PHONE, {}, "english")
    r = await handlers.handle_daily_summary(PHONE, {"period": "today"}, "english")
    assert '"my report"' not in r

    await database.close_db()
