"""Response templates in English and Nigerian Pidgin.

Design principles for low-literate users:
- Keep messages SHORT (2-3 lines max)
- Use simple, warm language
- Drip-feed tips (one hint per response, not a wall of instructions)
- Use emoji as visual anchors (checkmark, warning, money)
- Echo back what was heard on voice messages
- Never leave user at a dead end
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

    # === VOICE ECHO ===
    "voice_echo": {
        "pidgin": "I hear you say: \"{text}\"\n\n",
        "english": "I heard: \"{text}\"\n\n",
    },

    # === SALES ===
    "sale_recorded": {
        "pidgin": "Sold! {quantity} {unit} {product} = {total} naira{credit_note}",
        "english": "Sold! {quantity} {unit} {product} = {total} naira{credit_note}",
    },
    "sale_needs_price": {
        "pidgin": "How much you sell {product}? Just tell me the price.",
        "english": "How much did you sell {product} for?",
    },

    # === STOCK ===
    "stock_added": {
        "pidgin": "Stocked! {quantity} {unit} {product} added.{price_note}",
        "english": "Stocked! {quantity} {unit} {product} added.{price_note}",
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
        "pidgin": "No stock yet. Try: \"I buy 10 bag of rice\"",
        "english": "No stock yet. Try: \"I bought 10 bags of rice\"",
    },
    "stock_low": {
        "pidgin": "\n\n{product} almost finish! Only {quantity} {unit} remain.",
        "english": "\n\n{product} almost finished! Only {quantity} {unit} left.",
    },
    "stock_finished": {
        "pidgin": "\n\n{product} don finish for your record.",
        "english": "\n\n{product} is now finished in your records.",
    },
    "stock_oversold": {
        "pidgin": "\n\nCheck your stock: your record show you short by {quantity} {unit} of {product}.",
        "english": "\n\nCheck your stock: your records are short by {quantity} {unit} of {product}.",
    },

    # === CREDITS ===
    "credit_recorded": {
        "pidgin": "{customer} owe you {amount} naira.{note} Saved!",
        "english": "{customer} owes you {amount} naira.{note} Saved!",
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
        "pidgin": "{customer} don clear! No more debt.",
        "english": "{customer} all cleared! No more debt.",
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
        "pidgin": "I no see \"{customer}\" for your credit book. Try the name again?",
        "english": "I can't find \"{customer}\". Can you try the name again?",
    },

    # === EXPENSES ===
    "expense_recorded": {
        "pidgin": "Spent {amount} naira on {description}. Saved!",
        "english": "Spent {amount} naira on {description}. Saved!",
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
    "daily_summary_simple": {
        "pidgin": "{period} you sell {sales_count} things = {sales_total} naira.",
        "english": "{period} you sold {sales_count} things = {sales_total} naira.",
    },
    "daily_summary_with_expenses": {
        "pidgin": (
            "{period} you sell {sales_count} things = {sales_total} naira.\n"
            "You spend {expense_total} naira.\n"
            "Cash wey remain: {net_cash} naira."
        ),
        "english": (
            "{period} you sold {sales_count} things = {sales_total} naira.\n"
            "You spent {expense_total} naira.\n"
            "Cash in hand: {net_cash} naira."
        ),
    },
    "daily_summary_credits_line": {
        "pidgin": "\nPeople owe you {credit_total} naira.",
        "english": "\nPeople owe you {credit_total} naira.",
    },
    "daily_summary_payments_line": {
        "pidgin": "\nPeople pay you back {payment_total} naira.",
        "english": "\nPeople paid you back {payment_total} naira.",
    },
    "daily_summary_top": {
        "pidgin": "\n\nWetin sell pass:\n{top_products}",
        "english": "\n\nTop sellers:\n{top_products}",
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

    # === REPORT ===
    "report_link": {
        "pidgin": (
            "Here be your shop report:\n{url}\n\n"
            "E get all your sales, stock, credit and expenses. "
            "You fit open am anytime. No give the link to person wey you no trust."
        ),
        "english": (
            "Here is your shop report:\n{url}\n\n"
            "It shows all your sales, stock, credits and expenses. "
            "You can open it anytime. Only share the link with people you trust."
        ),
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
        "pidgin": "I no understand that one. Try something like:\n\"I sell 5 bag of rice, 2 thousand naira\"",
        "english": "I didn't get that. Try something like:\n\"I sold 5 bags of rice for 2 thousand naira\"",
    },

    # === CONFIRMATION ===
    "confirm_customer": {
        "pidgin": "You mean \"{matched}\"? I get somebody wey name like that already.\n\nSay \"yes\" if na the same person, or \"no\" if \"{original}\" na new person.",
        "english": "Did you mean \"{matched}\"? I have someone with a similar name.\n\nSay \"yes\" if it's the same person, or \"no\" if \"{original}\" is a new person.",
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
