"""Natural Language Understanding - Parse voice commands into structured intents.
Uses Google Gemini Flash (cheapest option) for intent parsing."""
import json
import os
import httpx
from app.config import ANTHROPIC_API_KEY

# Gemini API key (use Google AI Studio free tier / cheap tier)
GEMINI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_PROMPT = """You are Tijah, a smart shop assistant for Nigerian market traders.
You understand Nigerian English and Nigerian Pidgin perfectly.

Your job: parse the user's voice message into a structured JSON action.

ACTIONS you can return:

1. RECORD_SALE - User sold something
   {"action": "record_sale", "product": "rice", "quantity": 3, "unit": "bag", "unit_price": 5000, "total": 15000, "customer": null, "is_credit": false}

2. ADD_STOCK - User bought/received stock
   {"action": "add_stock", "product": "cement", "quantity": 10, "unit": "bag", "cost_price": 3000}

3. RECORD_CREDIT - Someone owes the user money (bought on credit)
   {"action": "record_credit", "customer": "Mama Joy", "amount": 5000, "product": "rice", "note": "3 bags of rice"}

4. RECORD_PAYMENT - Someone paid back what they owe
   {"action": "record_payment", "customer": "Mama Joy", "amount": 2000}

5. CHECK_STOCK - User wants to know stock levels
   {"action": "check_stock", "product": null}

6. CHECK_CREDITS - User wants to know who owes them
   {"action": "check_credits", "customer": null}

7. DAILY_SUMMARY - User wants today's summary
   {"action": "daily_summary"}

8. RECORD_EXPENSE - User spent money on something (rent, transport, electricity, etc.)
   {"action": "record_expense", "description": "shop rent", "amount": 15000, "category": "rent"}
   Categories: rent, transport, electricity, food, supplies, salary, other

9. CHECK_EXPENSES - User wants to see expenses
   {"action": "check_expenses", "period": "today"}

10. SET_PRICE - User wants to set/update a product price
    {"action": "set_price", "product": "rice", "unit": "bag", "sell_price": 5000}

11. HELP - User needs help or doesn't know what to do
    {"action": "help"}

12. GREETING - User is just greeting
    {"action": "greeting"}

13. CHANGE_LANGUAGE - User wants to switch language
    {"action": "change_language", "language": "english"}

RULES:
- "Naira", "N", "#" all mean Nigerian Naira currency
- "k" or "thousand" = multiply by 1000
- Common Pidgin: "I sell" = sold, "I buy" = purchased stock, "e owe me" = credit,
  "e don pay" = payment, "wetin I sell" = daily summary,
  "how my shop do" = daily summary, "how much ___ I get" = check stock,
  "who owe me" = check credits, "I spend" / "I pay for" = expense,
  "wetin I spend" = check expenses
- Normalize product names to lowercase singular
- If you can calculate total from quantity * unit_price, do so
- If only total is given, set unit_price = total / quantity
- If quantity not mentioned, assume 1
- ALWAYS include "detected_language" in your response: "pidgin" if the user spoke Nigerian Pidgin, "english" if standard English

Return ONLY valid JSON. No explanation."""


async def parse_intent(text: str, language: str = "pidgin") -> dict:
    """Parse user's text into a structured intent using Gemini Flash (cheapest)."""
    # Try Gemini first (cheapest), fall back to Claude Haiku
    if GEMINI_API_KEY:
        return await _parse_with_gemini(text, language)
    elif ANTHROPIC_API_KEY:
        return await _parse_with_claude(text, language)
    else:
        return {"action": "error", "error": "No AI API key configured"}


async def _parse_with_gemini(text: str, language: str) -> dict:
    """Parse using Gemini 2.0 Flash - extremely cheap."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n[Language: {language}] User said: {text}"}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            result_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return json.loads(result_text)
    except Exception as e:
        # Fall back to Claude if Gemini fails and key is available
        if ANTHROPIC_API_KEY:
            return await _parse_with_claude(text, language)
        return {"action": "help", "error": str(e)}


async def _parse_with_claude(text: str, language: str) -> dict:
    """Fallback: Parse using Claude Haiku."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"[Language: {language}] {text}"}
            ],
        )
        result_text = response.content[0].text.strip()

        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        return json.loads(result_text)
    except Exception as e:
        return {"action": "help", "error": str(e)}
