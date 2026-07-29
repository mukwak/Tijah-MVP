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
            "How far! I be Tijah, your shop helper.\n\n"
            "Voice note or text, just tell me wetin you sell, buy, or who owe you. "
            "Your record na private. Say \"I get complaint\" if anything no work.\n\n"
            "Wetin you sell today?"
        ),
        "english": (
            "Hi! I'm Tijah, your shop helper.\n\n"
            "Voice note or text - just tell me what you sell, buy, or who owes you. "
            "Your records are private. Say \"I have a complaint\" if anything goes wrong.\n\n"
            "What did you sell today?"
        ),
    },
    "welcome_after_action": {
        "pidgin": (
            "\n\nBy the way - I be Tijah, your shop helper! "
            "I go keep all your sales, stock, and credit records. "
            "Your data na private. Just yarn to me anytime."
        ),
        "english": (
            "\n\nBy the way - I'm Tijah, your shop helper! "
            "I'll keep all your sales, stock, and credit records. "
            "Your data is private. Just talk to me anytime."
        ),
    },

    # === VOICE ECHO ===
    "voice_echo": {
        "pidgin": "I hear you say: \"{text}\"\n\n",
        "english": "I heard: \"{text}\"\n\n",
    },

    # === SALES ===
    "sale_recorded": {
        "pidgin": "Sold! {quantity} {unit} {product}{price_detail} = {total} naira{credit_note}",
        "english": "Sold! {quantity} {unit} {product}{price_detail} = {total} naira{credit_note}",
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

    # === FEEDBACK ===
    "feedback_saved": {
        "pidgin": (
            "Thank you! I don send your complaint to the Tijah team. "
            "Dem go look am well. Anything else?"
        ),
        "english": (
            "Thank you! I've sent your feedback to the Tijah team. "
            "They'll look into it. Anything else?"
        ),
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
            "\"How my shop do today?\"\n"
            "\"My report\" - see all your records\n"
            "\"Cancel am\" - if you make mistake\n\n"
            "Voice note or text, I go understand."
        ),
        "english": (
            "I'm Tijah! Just talk to me normally, like:\n\n"
            "\"I sold 3 bags of rice for 5 thousand\"\n"
            "\"I bought 10 bags of cement\"\n"
            "\"Mama Joy owes me 5 thousand\"\n"
            "\"How did my shop do today?\"\n"
            "\"My report\" - see all your records\n"
            "\"Cancel that\" - if you make a mistake\n\n"
            "Voice note or text, I'll understand."
        ),
    },

    # === GREETING ===
    "greeting": {
        "pidgin": "How far! Wetin you sell today?",
        "english": "Hi! What did you sell today?",
    },

    # === SHOP NAME ===
    "shop_name_set": {
        "pidgin": "I don save am! Your shop name na {name}. E go show for your report.",
        "english": "Saved! Your shop name is {name}. It will show on your report.",
    },
    "shop_name_ask": {
        "pidgin": "\n\nWetin be your shop name? Tell me like \"my shop name na Mama T Store\" - e go show for the top of your report.",
        "english": "\n\nWhat is your shop's name? Tell me like \"my shop name is Mama T Store\" - it will show at the top of your report.",
    },

    # === LANGUAGE ===
    "language_changed": {
        "pidgin": "Okay! We go yarn Pidgin.",
        "english": "Okay! I'll speak English.",
    },

    # === ERRORS ===
    "error": {
        "pidgin": "Sorry, something no work. Try again? If e still no work, tell me \"I get complaint\".",
        "english": "Sorry, something went wrong. Try again? If it still fails, tell me \"I have a complaint\".",
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
    "hint_stock_unknown": {
        "pidgin": "\n\nIf you tell me how many {product} you get, I go dey count am and warn you before e finish.",
        "english": "\n\nIf you tell me how many {product} you have, I can keep count and warn you when it's running out.",
    },
    "hint_set_price": {
        "pidgin": "\n\nWetin be {product} price? Tell me like \"{product} price na 500 per {unit}\" - next time I go record your sales sharp-sharp.",
        "english": "\n\nWhat price do you sell {product}? Tell me like \"{product} price is 500 per {unit}\" - then I can record your sales faster.",
    },
    "hint_after_expense": {
        "pidgin": "\n\nAsk me \"how my shop do today?\" anytime to see your cash.",
        "english": "\n\nAsk me \"how did my shop do today?\" anytime to see your cash.",
    },
    "hint_undo": {
        "pidgin": "\n\nIf I hear am wrong, just talk \"cancel am\" and I go remove am.",
        "english": "\n\nIf I got anything wrong, just say \"cancel that\" and I'll remove it.",
    },
    "hint_report": {
        "pidgin": "\n\nTalk \"my report\" anytime make you see all your records for one page.",
        "english": "\n\nSay \"my report\" anytime to see all your records on one page.",
    },
    "hint_credit_reminder": {
        "pidgin": "\n\nIf you want make I write reminder message, just talk \"remind {customer}\".",
        "english": "\n\nWant me to write a reminder message? Just say \"remind {customer}\".",
    },
    "hint_voice_name_check": {
        "pidgin": "\n\nI hear \"{customer}\" - if the name no correct, tell me \"change {customer} to (correct name)\".",
        "english": "\n\nI heard \"{customer}\" - if that's wrong, say \"change {customer} to (correct name)\".",
    },
    "hint_voice_name_spell": {
        "pidgin": "\n\nVoice fit change name small. Try type the name instead.",
        "english": "\n\nVoice can change names slightly. Try typing the name instead.",
    },

    # === INSIGHTS (one simple line, only when there is data to compare) ===
    "insight_better": {
        "pidgin": "\n\nE better pass {prev_label} ({prev_total} naira). Well done!",
        "english": "\n\nThat's better than {prev_label} ({prev_total} naira). Well done!",
    },
    "insight_less": {
        "pidgin": "\n\n{prev_label} you do {prev_total} naira.",
        "english": "\n\n{prev_label} was {prev_total} naira.",
    },

    # === CUSTOMER RECEIPT ===
    "customer_receipt_link": {
        "pidgin": (
            "Here be {customer} receipt:\n{url}\n\n"
            "E show wetin {customer} owe and wetin e don pay. "
            "You fit send the link give am."
        ),
        "english": (
            "Here is {customer}'s receipt:\n{url}\n\n"
            "It shows what {customer} owes and what they've paid. "
            "You can share this link with them."
        ),
    },

    # === DAILY NUDGE ===
    "nudge_evening_active": {
        "pidgin": (
            "Good evening! Today you record {sales_count} sales = {sales_total} naira. "
            "Well done! Anything wey you sell wey you never tell me?"
        ),
        "english": (
            "Good evening! Today you recorded {sales_count} sales = {sales_total} naira. "
            "Well done! Did you sell anything else you haven't told me?"
        ),
    },
    "nudge_evening_idle": {
        "pidgin": "Good evening! You never record anything today. Wetin you sell?",
        "english": "Good evening! You haven't recorded anything today. What did you sell?",
    },

    # === PROGRESSIVE DISCOVERY HINTS ===
    "hint_discover_expenses": {
        "pidgin": "\n\nYou sabi say you fit tell me your expenses too? Like \"I spend 500 on transport\".",
        "english": "\n\nDid you know you can track expenses too? Like \"I spent 500 on transport\".",
    },
    "hint_discover_stock": {
        "pidgin": "\n\nIf you tell me when you buy stock, I go warn you before e finish. Try: \"I buy 10 bag rice\".",
        "english": "\n\nIf you tell me when you buy stock, I'll warn you before it runs out. Try: \"I bought 10 bags of rice\".",
    },
    "hint_discover_receipt": {
        "pidgin": "\n\nYou fit get receipt for any customer wey owe you. Just talk \"receipt for {customer}\".",
        "english": "\n\nYou can get a receipt for any customer who owes you. Just say \"receipt for {customer}\".",
    },
    "hint_discover_backdate": {
        "pidgin": "\n\nIf you sell something yesterday, just talk am so: \"I sell rice yesterday\".",
        "english": "\n\nIf you sold something yesterday, just say so: \"I sold rice yesterday\".",
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
