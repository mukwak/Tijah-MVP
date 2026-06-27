"""Local CLI simulator - test Tijah without WhatsApp.

Usage: python test_local.py
Type messages as if you're a shop owner. Supports text only (no voice in CLI).
"""
import asyncio
import sys
from app.database import get_db, close_db
from app.nlu import parse_intent
from app.responses import get_response
from app import handlers
from app.main import _route_intent

TEST_PHONE = "2348012345678"


async def setup_shop():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM shops WHERE phone = ?", (TEST_PHONE,))
    if not await cursor.fetchone():
        await db.execute(
            "INSERT INTO shops (phone, name, language, onboarded) VALUES (?, ?, ?, 1)",
            (TEST_PHONE, "Test Shop", "pidgin", 1),
        )
        await db.commit()
        print("Created test shop.\n")


async def main():
    print("=" * 50)
    print("  TIJAH - Local Test Simulator")
    print("  Type messages like a shop owner would")
    print("  Type 'quit' to exit, 'lang en' or 'lang pidgin' to switch")
    print("=" * 50)
    print()

    await setup_shop()
    db = await get_db()
    lang = "pidgin"

    # Show help first
    print(f"TIJAH: {get_response('greeting', lang)}\n")

    while True:
        try:
            user_input = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower().startswith("lang "):
            lang = user_input[5:].strip()
            cursor = await db.execute("SELECT phone FROM shops WHERE phone = ?", (TEST_PHONE,))
            if await cursor.fetchone():
                await db.execute("UPDATE shops SET language = ? WHERE phone = ?", (lang, TEST_PHONE))
                await db.commit()
            print(f"TIJAH: Language set to {lang}\n")
            continue

        # Parse intent
        intent = await parse_intent(user_input, lang)
        print(f"  [Intent: {intent}]")

        # Route to handler
        response = await _route_intent(TEST_PHONE, intent, lang)
        print(f"TIJAH: {response}\n")

    await close_db()
    print("\nBye bye!")


if __name__ == "__main__":
    asyncio.run(main())
