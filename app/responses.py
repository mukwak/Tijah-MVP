"""Response templates in English and Nigerian Pidgin.

Design principles for low-literate users:
- Keep messages SHORT (2-3 lines max)
- Use simple, warm language
- Drip-feed tips (one hint per response, not a wall of instructions)
- Use emoji as visual anchors sparingly
"""

RESPONSES = {
    # === ONBOARDING ===
    "welcome": {
        "pidgin": (
            "Hey! I be Tijah, your shop helper.\n\n"
            "Anytime you sell something, just send me voice note. I go record am for you.\n\n"
            "Try am now - tell me wetin you sell today!"
        ),
        "english": (
            "Hi! I'm Tijah, your shop helper.\n\n"
            "Anytime you sell something, just send me a voice note. I'll record it for you.\n\n"
            "Try it now - tell me what you sold today!"
        ),
    },
    "shop_name_saved": {
        "pidgin": "Nice one! Your shop na \"{name}\". Start telling me wetin you sell!",
        "english": "Nice! Your shop is \"{name}\". Start telling me what you sell!",
    },

    # === SALES ===
    "sale_recorded": {
        "pidgin": "{quantity} {unit} {product} = {total} naira. Done!{credit_note}",
        "english": "{quantity} {unit} {product} = {total} naira. Done!{credit_note}",
    },
    "sale_needs_price": {
        "pidgin": "How much you sell {product}? Just tell me the price.",
        "english": "How much did you sell {product} for?",
    },

    # === STOCK ===
    "stock_added": {
        "pidgin": "{quantity} {unit} {product} added to your stock.{price_note}",
        "english": "{quantity} {unit} {product} added to your stock.{price_note}",
    },
    "stock_check_single": {
        "pidgin": "You get {quantity} {unit} of {product}.",
        "english": "You have {quantity} {unit} of {product}.",
    },
    "stock_check_all": {
        "pidgin": "Your stock:\n{stock_list}",
        "english": "Your stock:\n{stock_list}",
    },
    "stock_empty": {
        "pidgin": "You never add any stock yet. When you buy goods, tell me!",
        "english": "No stock yet. When you buy goods, tell me!",
    },
    "stock_low": {
        "pidgin": "Heads up! {product} almost finish - only {quantity} {unit} remain.",
        "english": "Heads up! {product} almost finished - only {quantity} {unit} left.",
    },

    # === CREDITS ===
    "credit_recorded": {
        "pidgin": "{customer} owe you {amount} naira.{note} I don save am.",
        "english": "{customer} owes you {amount} naira.{note} Saved.",
    },
    "payment_recorded": {
        "pidgin": "{customer} pay {amount} naira. {remaining_note}",
        "english": "{customer} paid {amount} naira. {remaining_note}",
    },
    "remaining_debt": {
        "pidgin": "E still owe you {remaining} naira.",
        "english": "Still owing {remaining} naira.",
    },
    "debt_cleared": {
        "pidgin": "{customer} don pay everything! No more debt.",
        "english": "{customer} paid everything! No more debt.",
    },
    "credits_list": {
        "pidgin": "People wey owe you:\n{credit_list}\n\nTotal: {total} naira",
        "english": "People owing you:\n{credit_list}\n\nTotal: {total} naira",
    },
    "credits_empty": {
        "pidgin": "Nobody owe you money. Na good thing!",
        "english": "Nobody owes you money. That's good!",
    },
    "customer_not_found": {
        "pidgin": "I no see {customer} for your credit book. Check the name again?",
        "english": "I can't find {customer}. Can you check the name?",
    },

    # === EXPENSES ===
    "expense_recorded": {
        "pidgin": "You spend {amount} naira on {description}. Saved.",
        "english": "You spent {amount} naira on {description}. Saved.",
    },
    "expenses_list": {
        "pidgin": "You spend {period}:\n{expense_list}\n\nTotal: {total} naira",
        "english": "You spent {period}:\n{expense_list}\n\nTotal: {total} naira",
    },
    "expenses_empty": {
        "pidgin": "No expenses {period}.",
        "english": "No expenses {period}.",
    },

    # === DAILY SUMMARY ===
    "daily_summary": {
        "pidgin": (
            "Today so far:\n\n"
            "You sell {sales_count} things = {sales_total} naira\n"
            "You spend {expense_total} naira\n"
            "People owe you {credit_total} naira\n"
            "People pay you back {payment_total} naira\n\n"
            "Cash wey enter: {net_cash} naira\n"
            "{top_products}"
        ),
        "english": (
            "Today so far:\n\n"
            "You sold {sales_count} things = {sales_total} naira\n"
            "You spent {expense_total} naira\n"
            "Credit given: {credit_total} naira\n"
            "Payments received: {payment_total} naira\n\n"
            "Cash in hand: {net_cash} naira\n"
            "{top_products}"
        ),
    },
    "no_activity": {
        "pidgin": "Nothing recorded today yet. When you sell something, just tell me!",
        "english": "Nothing recorded today yet. When you sell something, just tell me!",
    },

    # === PRICE ===
    "price_set": {
        "pidgin": "{product} price set to {price} naira per {unit}.",
        "english": "{product} price set to {price} naira per {unit}.",
    },

    # === HELP ===
    "help": {
        "pidgin": (
            "I be Tijah! Just talk to me normal, like:\n\n"
            "\"I sell 3 bag of rice, 5 thousand\"\n"
            "\"I buy 10 bag cement\"\n"
            "\"Mama Joy owe me 5 thousand\"\n"
            "\"How my shop do today?\"\n\n"
            "Voice note or text, I go understand."
        ),
        "english": (
            "I'm Tijah! Just talk to me normally, like:\n\n"
            "\"I sold 3 bags of rice for 5 thousand\"\n"
            "\"I bought 10 bags of cement\"\n"
            "\"Mama Joy owes me 5 thousand\"\n"
            "\"How did my shop do today?\"\n\n"
            "Voice note or text, I'll understand."
        ),
    },

    # === GREETING ===
    "greeting": {
        "pidgin": "How far! Wetin you sell today?",
        "english": "Hi! What did you sell today?",
    },

    # === LANGUAGE ===
    "language_changed": {
        "pidgin": "Okay! We go yarn Pidgin.",
        "english": "Okay! I'll speak English.",
    },

    # === ERRORS ===
    "error": {
        "pidgin": "Sorry, something no work. Try again?",
        "english": "Sorry, something went wrong. Try again?",
    },
    "not_understood": {
        "pidgin": "I no understand. Try tell me again?",
        "english": "I didn't get that. Can you try again?",
    },

    # === HINTS (drip-fed after actions) ===
    "hint_after_sale": {
        "pidgin": "\n\nYou fit also tell me who owe you money.",
        "english": "\n\nYou can also tell me who owes you money.",
    },
    "hint_after_stock": {
        "pidgin": "\n\nWhen you sell from this stock, just tell me!",
        "english": "\n\nWhen you sell from this stock, just tell me!",
    },
    "hint_after_credit": {
        "pidgin": "\n\nWhen {customer} pay, just tell me.",
        "english": "\n\nWhen {customer} pays, just tell me.",
    },
}


def get_response(key: str, language: str = "english", **kwargs) -> str:
    """Get a response template and format it."""
    template = RESPONSES.get(key, RESPONSES["error"])
    if isinstance(template, dict):
        text = template.get(language, template.get("english", ""))
    else:
        text = template
    try:
        return text.format(**kwargs) if kwargs else text
    except KeyError:
        return text
