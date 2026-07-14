import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest

from app import database, handlers, report
from app.preclassifier import preclassify


@pytest.mark.asyncio
async def test_report_token_and_html(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.close_db()

    db = await database.get_db()
    await db.execute(
        "INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
        ("2348000000001", "Mama T Shop", "english"),
    )
    await db.commit()

    token = await report.get_or_create_report_token("2348000000001")
    assert len(token) >= 16
    # Stable: asking again returns the same token
    assert await report.get_or_create_report_token("2348000000001") == token
    assert await report.get_phone_by_token(token) == "2348000000001"
    assert await report.get_phone_by_token("nope") is None

    # Add some data and render
    await handlers.handle_add_stock(
        "2348000000001", {"product": "rice", "quantity": 5, "unit": "bag", "cost_price": 3000}, "english")
    await handlers.handle_record_sale(
        "2348000000001", {"product": "rice", "quantity": 2, "unit": "bag", "unit_price": 5000}, "english")
    await handlers.handle_record_expense(
        "2348000000001", {"description": "transport", "amount": 500, "category": "transport"}, "english")

    html_out = await report.render_report_html("2348000000001")
    assert "Mama T Shop" in html_out
    assert "rice" in html_out
    assert "10,000" in html_out  # sale total
    assert "transport" in html_out

    await database.close_db()


@pytest.mark.asyncio
async def test_get_report_handler_returns_link(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.close_db()

    db = await database.get_db()
    await db.execute(
        "INSERT INTO shops (phone, onboarded) VALUES (?, 1)", ("2348000000002",))
    await db.commit()

    response = await handlers.handle_get_report("2348000000002", {}, "english")
    assert "/report/" in response

    await database.close_db()


def test_preclassifier_matches_report_requests():
    assert preclassify("my report") == {"action": "get_report"}
    assert preclassify("send me my report") == {"action": "get_report"}
    assert preclassify("I sold 3 bags of rice") is None
