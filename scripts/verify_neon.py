"""One-off verification that core flows work against the real Neon Postgres.

Uses a synthetic test phone and deletes its data afterwards.
Run: python -m scripts.verify_neon
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
    sys.exit("DATABASE_URL is not a Postgres URL - aborting")

from app import database, handlers, report  # noqa: E402

TEST_PHONE = "2340000TEST01"


async def cleanup(db):
    for table in ("sales", "stock_entries", "credits", "payments", "expenses",
                  "pending_actions", "report_tokens", "products", "shops"):
        await db.execute(f"DELETE FROM {table} WHERE phone = ?", (TEST_PHONE,))


async def main():
    db = await database.get_db()
    print(f"Connected. backend={db.backend}")
    assert db.backend == "postgres", "Expected Postgres backend"

    await cleanup(db)

    await db.execute("INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
                     (TEST_PHONE, "Verify Shop", "english"))

    print("dedupe:", await database.try_mark_message_processed("wamid.verify.1"),
          await database.try_mark_message_processed("wamid.verify.1"))

    r = await handlers.handle_add_stock(
        TEST_PHONE, {"product": "rice", "quantity": 5, "unit": "bag", "cost_price": 3000}, "english")
    print("add_stock:", r.replace("\n", " | "))

    r = await handlers.handle_record_sale(
        TEST_PHONE, {"product": "rice", "quantity": 2, "unit": "bag", "unit_price": 5000}, "english")
    print("record_sale:", r.replace("\n", " | "))

    r = await handlers.handle_record_credit(
        TEST_PHONE, {"customer": "Mama Joy", "amount": 5000, "note": "1 bag rice"}, "english")
    print("record_credit:", r.replace("\n", " | "))

    r = await handlers.handle_record_payment(
        TEST_PHONE, {"customer": "Mama Joy", "amount": 2000}, "english")
    print("record_payment:", r.replace("\n", " | "))

    r = await handlers.handle_record_expense(
        TEST_PHONE, {"description": "transport", "amount": 500, "category": "transport"}, "english")
    print("record_expense:", r.replace("\n", " | "))

    r = await handlers.handle_daily_summary(TEST_PHONE, {"period": "today"}, "english")
    print("daily_summary:", r.replace("\n", " | "))

    r = await handlers.handle_check_stock(TEST_PHONE, {}, "english")
    print("check_stock:", r.replace("\n", " | "))

    r = await handlers.handle_check_credits(TEST_PHONE, {}, "english")
    print("check_credits:", r.replace("\n", " | "))

    token = await report.get_or_create_report_token(TEST_PHONE)
    html = await report.render_report_html(TEST_PHONE)
    assert "Verify Shop" in html and "rice" in html and "Mama Joy" in html
    print(f"report: token ok ({len(token)} chars), html ok ({len(html)} bytes)")

    r = await handlers.handle_get_report(TEST_PHONE, {}, "english")
    print("get_report:", r.split(chr(10))[1])

    await cleanup(db)
    await db.execute("DELETE FROM processed_messages WHERE message_id = ?", ("wamid.verify.1",))
    await database.close_db()
    print("\nALL CHECKS PASSED - Neon Postgres works end-to-end")


asyncio.run(main())
