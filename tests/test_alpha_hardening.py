import hashlib
import hmac
import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest

from app import database
from app import handlers
from app import main


class DummyRequest:
    def __init__(self, headers):
        self.headers = headers


def test_webhook_signature_verification_accepts_valid_signature(monkeypatch):
    raw_body = b'{"entry":[]}'
    secret = "secret"
    signature = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    request = DummyRequest({"x-hub-signature-256": f"sha256={signature}"})

    monkeypatch.setattr(main, "VERIFY_WEBHOOK_SIGNATURE", True)
    monkeypatch.setattr(main, "WHATSAPP_APP_SECRET", secret)

    assert main._verify_webhook_signature(request, raw_body) is True


def test_webhook_signature_verification_rejects_invalid_signature(monkeypatch):
    request = DummyRequest({"x-hub-signature-256": "sha256=bad"})

    monkeypatch.setattr(main, "VERIFY_WEBHOOK_SIGNATURE", True)
    monkeypatch.setattr(main, "WHATSAPP_APP_SECRET", "secret")

    assert main._verify_webhook_signature(request, b"{}") is False


def test_postgres_translation_uses_payment_ledger_and_returning_id():
    sql = database._translate_sqlite_query(
        "INSERT INTO products (phone, name, unit, sell_price, cost_price) VALUES (?, ?, ?, ?, ?)"
    )

    assert "RETURNING id" in sql
    assert database._convert_placeholders("SELECT * FROM sales WHERE phone = ? AND id = ?") == (
        "SELECT * FROM sales WHERE phone = $1 AND id = $2"
    )


@pytest.mark.asyncio
async def test_sqlite_dedupe_and_oversell_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", "")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.close_db()

    db = await database.get_db()
    await db.execute(
        "INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
        ("2348000000000", "Test Shop", "english"),
    )
    await db.commit()

    assert await database.try_mark_message_processed("wamid.1") is True
    assert await database.try_mark_message_processed("wamid.1") is False

    await handlers.handle_add_stock(
        "2348000000000",
        {"product": "rice", "quantity": 1, "unit": "bag"},
        "english",
    )
    response = await handlers.handle_record_sale(
        "2348000000000",
        {"product": "rice", "quantity": 2, "unit": "bag", "unit_price": 1000},
        "english",
    )

    assert "short by 1 bag of rice" in response

    await database.close_db()
