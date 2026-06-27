"""Response templates in English and Nigerian Pidgin."""

RESPONSES = {
    # === ONBOARDING ===
    "welcome": {
        "pidgin": (
            "Hey! Welcome to Tijah! I be your shop assistant wey go help you manage your business.\n\n"
            "You fit send me voice message or text to:\n"
            "- Record wetin you sell\n"
            "- Track who owe you money\n"
            "- Know how much stock you get\n"
            "- Track your expenses\n"
            "- Check how your shop do for today\n\n"
            "Just talk to me like you dey talk to your friend!\n\n"
            "Wetin be your shop name?"
        ),
        "english": (
            "Hello! Welcome to Tijah! I'm your shop assistant that helps you manage your business.\n\n"
            "You can send me voice message or text to:\n"
            "- Record your sales\n"
            "- Track who owes you\n"
            "- Know your stock levels\n"
            "- Track your expenses\n"
            "- Check your daily summary\n\n"
            "Just talk to me like a friend!\n\n"
            "What is your shop name?"
        ),
    },
    "shop_name_saved": {
        "pidgin": "Nice one! I don save your shop name as \"{name}\". You don ready! Just send me voice note or text anytime.",
        "english": "Great! I've saved your shop name as \"{name}\". You're all set! Just send me a voice note or text anytime.",
    },

    # === SALES ===
    "sale_recorded": {
        "pidgin": "I don record am! You sell {quantity} {unit} of {product} for {total} naira.{credit_note}",
        "english": "Recorded! You sold {quantity} {unit} of {product} for {total} naira.{credit_note}",
    },
    "sale_needs_price": {
        "pidgin": "How much you sell {product}? Tell me like: \"I sell {product} for 2 thousand naira\"",
        "english": "What price did you sell {product} for? Tell me like: \"I sold {product} for 2 thousand naira\"",
    },
    "credit_note_pidgin": "\n{customer} buy am on credit.",
    "credit_note_english": "\n{customer} bought on credit.",

    # === STOCK ===
    "stock_added": {
        "pidgin": "I don add am! {quantity} {unit} of {product} don enter your stock.{price_note}",
        "english": "Added! {quantity} {unit} of {product} added to your stock.{price_note}",
    },
    "stock_check_single": {
        "pidgin": "You get {quantity} {unit} of {product} for store.",
        "english": "You have {quantity} {unit} of {product} in stock.",
    },
    "stock_check_all": {
        "pidgin": "Your stock list:\n{stock_list}\n\nTotal: {count} different items for store.",
        "english": "Your stock list:\n{stock_list}\n\nTotal: {count} different items in stock.",
    },
    "stock_empty": {
        "pidgin": "You never add any stock. Send me voice note like: \"I buy 10 bag of rice, 3 thousand each\"",
        "english": "You haven't added any stock yet. Send me a voice note like: \"I bought 10 bags of rice at 3 thousand each\"",
    },
    "stock_low": {
        "pidgin": "Warning! {product} don dey low - you only get {quantity} {unit} remain.",
        "english": "Warning! {product} is running low - only {quantity} {unit} left.",
    },

    # === CREDITS ===
    "credit_recorded": {
        "pidgin": "I don record am. {customer} owe you {amount} naira.{note}",
        "english": "Recorded. {customer} owes you {amount} naira.{note}",
    },
    "payment_recorded": {
        "pidgin": "I don record payment. {customer} don pay {amount} naira. {remaining_note}",
        "english": "Payment recorded. {customer} paid {amount} naira. {remaining_note}",
    },
    "remaining_debt": {
        "pidgin": "E still owe you {remaining} naira.",
        "english": "They still owe you {remaining} naira.",
    },
    "debt_cleared": {
        "pidgin": "{customer} don pay everything! No more debt.",
        "english": "{customer} has paid in full! No more debt.",
    },
    "credits_list": {
        "pidgin": "People wey owe you:\n{credit_list}\n\nTotal: {total} naira",
        "english": "People who owe you:\n{credit_list}\n\nTotal: {total} naira",
    },
    "credits_empty": {
        "pidgin": "Nobody owe you money right now. Na good thing!",
        "english": "Nobody owes you money right now. That's good!",
    },
    "customer_not_found": {
        "pidgin": "I no see {customer} for your credit book. You sure say na the correct name?",
        "english": "I can't find {customer} in your credit book. Are you sure that's the right name?",
    },

    # === EXPENSES ===
    "expense_recorded": {
        "pidgin": "I don record your expense. You spend {amount} naira for {description}.",
        "english": "Expense recorded. You spent {amount} naira on {description}.",
    },
    "expenses_list": {
        "pidgin": "Your expenses {period}:\n{expense_list}\n\nTotal wey you spend: {total} naira",
        "english": "Your expenses {period}:\n{expense_list}\n\nTotal spent: {total} naira",
    },
    "expenses_empty": {
        "pidgin": "You never record any expense {period}.",
        "english": "No expenses recorded {period}.",
    },

    # === DAILY SUMMARY ===
    "daily_summary": {
        "pidgin": (
            "How your shop do today:\n\n"
            "Sales: {sales_count} sales = {sales_total} naira\n"
            "Expenses: {expense_total} naira\n"
            "Credit wey people take: {credit_total} naira\n"
            "Payment wey come in: {payment_total} naira\n\n"
            "Cash wey enter: {net_cash} naira\n"
            "{top_products}"
        ),
        "english": (
            "Your shop summary today:\n\n"
            "Sales: {sales_count} sales = {sales_total} naira\n"
            "Expenses: {expense_total} naira\n"
            "Credit given: {credit_total} naira\n"
            "Payments received: {payment_total} naira\n\n"
            "Net cash in: {net_cash} naira\n"
            "{top_products}"
        ),
    },
    "no_activity": {
        "pidgin": "You never do anything for shop today. When you sell or buy something, send me voice note!",
        "english": "No activity recorded today. When you make a sale or purchase, send me a voice note!",
    },

    # === PRICE ===
    "price_set": {
        "pidgin": "I don set the price. {product} na {price} naira per {unit} now.",
        "english": "Price updated. {product} is now {price} naira per {unit}.",
    },

    # === HELP ===
    "help": {
        "pidgin": (
            "I be Tijah, your shop helper! You fit tell me:\n\n"
            "SELL: \"I sell 3 bag of rice, 5 thousand naira\"\n"
            "BUY STOCK: \"I buy 10 bag cement, 3 thousand each\"\n"
            "CREDIT: \"Mama Joy owe me 5 thousand for rice\"\n"
            "PAYMENT: \"Mama Joy don pay 2 thousand\"\n"
            "EXPENSE: \"I pay 15 thousand for rent\" or \"I spend 2k for transport\"\n"
            "CHECK STOCK: \"How many rice I get?\"\n"
            "WHO OWE ME: \"Who owe me money?\"\n"
            "MY EXPENSES: \"Wetin I spend today?\"\n"
            "TODAY: \"How my shop do today?\"\n\n"
            "Just send voice note - na the easiest way!"
        ),
        "english": (
            "I'm Tijah, your shop helper! You can tell me:\n\n"
            "SELL: \"I sold 3 bags of rice for 5 thousand naira\"\n"
            "BUY STOCK: \"I bought 10 bags of cement at 3 thousand each\"\n"
            "CREDIT: \"Mama Joy owes me 5 thousand for rice\"\n"
            "PAYMENT: \"Mama Joy paid 2 thousand\"\n"
            "EXPENSE: \"I paid 15 thousand for rent\" or \"I spent 2k on transport\"\n"
            "CHECK STOCK: \"How much rice do I have?\"\n"
            "WHO OWES: \"Who owes me money?\"\n"
            "MY EXPENSES: \"What did I spend today?\"\n"
            "TODAY: \"How did my shop do today?\"\n\n"
            "Just send a voice note - it's the easiest way!"
        ),
    },

    # === GREETING ===
    "greeting": {
        "pidgin": "How far! Wetin you wan do for shop today? Just send me voice note or text.",
        "english": "Hello! What would you like to do today? Just send me a voice note or text.",
    },

    # === LANGUAGE ===
    "language_changed": {
        "pidgin": "I don change to Pidgin. We go yarn Pidgin from now!",
        "english": "Changed to English. I'll respond in English from now on!",
    },

    # === ERRORS ===
    "error": {
        "pidgin": "Sorry, something no work well. Try send your message again.",
        "english": "Sorry, something went wrong. Please try sending your message again.",
    },
    "not_understood": {
        "pidgin": "I no understand wetin you talk. You fit try again? Or send \"help\" make I show you wetin I fit do.",
        "english": "I didn't understand that. Can you try again? Or send \"help\" to see what I can do.",
    },
}


def get_response(key: str, language: str = "pidgin", **kwargs) -> str:
    """Get a response template and format it."""
    template = RESPONSES.get(key, RESPONSES["error"])
    if isinstance(template, dict):
        text = template.get(language, template.get("pidgin", ""))
    else:
        text = template
    try:
        return text.format(**kwargs) if kwargs else text
    except KeyError:
        return text
