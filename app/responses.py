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
            "I go save only wetin you tell me, and I only use am to help your shop. "
            "Say \"my privacy\" to learn more, or \"I get complaint\" if anything no work.\n\n"
            "Wetin you sell today?"
        ),
        "english": (
            "Hi! I'm Tijah, your shop helper.\n\n"
            "Voice note or text - just tell me what you sell, buy, or who owes you. "
            "I only save what you tell me, and I only use it to help your shop. "
            "Say \"my privacy\" to learn more, or \"I have a complaint\" if anything goes wrong.\n\n"
            "What did you sell today?"
        ),
    },
    "welcome_after_action": {
        "pidgin": (
            "\n\nBy the way - I be Tijah, your shop helper! "
            "I only save wetin you tell me, and I only use am to help your shop. "
            "If anything no work, tell me \"I get complaint\"."
        ),
        "english": (
            "\n\nBy the way - I'm Tijah, your shop helper! "
            "I only save what you tell me, and I only use it to help your shop. "
            "If anything goes wrong, tell me \"I have a complaint\"."
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
        "pidgin": "{period} you sell {sales_count} items = {sales_total} naira.",
        "english": "{period} you sold {sales_count} items = {sales_total} naira.",
    },
    "daily_summary_with_expenses": {
        "pidgin": (
            "{period} you sell {sales_count} items = {sales_total} naira.\n"
            "You spend {expense_total} naira.\n"
            "Cash wey remain: {net_cash} naira."
        ),
        "english": (
            "{period} you sold {sales_count} items = {sales_total} naira.\n"
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
            "Thank you! I don send your complaint to the Tijah team:\n\n"
            "\"{message}\"\n\n"
            "Dem go look am well. Anything else?"
        ),
        "english": (
            "Thank you! I've sent your feedback to the Tijah team:\n\n"
            "\"{message}\"\n\n"
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
            "\"Cancel am\" - if you make mistake\n"
            "\"I get complaint\" - if something no work\n\n"
            "Voice note or text, I go understand."
        ),
        "english": (
            "I'm Tijah! Just talk to me normally, like:\n\n"
            "\"I sold 3 bags of rice for 5 thousand\"\n"
            "\"I bought 10 bags of cement\"\n"
            "\"Mama Joy owes me 5 thousand\"\n"
            "\"How did my shop do today?\"\n"
            "\"My report\" - see all your records\n"
            "\"Cancel that\" - if you make a mistake\n"
            "\"I have a complaint\" - if something goes wrong\n\n"
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
    "clarify": {
        "pidgin": "I no understand that one well. Try tell me again, like \"I sell 3 bag rice, 5 thousand.\"",
        "english": "I didn't quite get that. Try again, like \"I sold 3 bags of rice for 5 thousand.\"",
    },
    "off_topic": {
        "pidgin": "I be your shop assistant o! I fit help you record sales, check stock, track who owe you, and manage your shop. Wetin you sell today?",
        "english": "I'm your shop assistant! I can help you record sales, check stock, track who owes you, and manage your shop. What did you sell today?",
    },
    "clarify_intent": {
        "pidgin": "You mean say {description}? Say \"yes\" or tell me again.",
        "english": "Did you mean to {description}? Say \"yes\" or tell me again.",
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
            "Good evening! Today you sell {sales_count} items = {sales_total} naira. "
            "Well done! Anything wey you sell wey you never tell me?"
        ),
        "english": (
            "Good evening! Today you sold {sales_count} items = {sales_total} naira. "
            "Well done! Did you sell anything else you haven't told me?"
        ),
    },
    "nudge_evening_idle": {
        "pidgin": "Good evening! You never record anything today. Wetin you sell?",
        "english": "Good evening! You haven't recorded anything today. What did you sell?",
    },
    # === PRIVACY & DATA ===
    "privacy_summary": {
        "pidgin": (
            "Wetin I save: your phone number, sales, stock, expenses, customer names, and wetin you tell me by voice or text.\n\n"
            "Why: to help you track your shop.\n\n"
            "Who fit see am: only you — through your phone or your report link.\n\n"
            "I no dey sell or share your data with anybody.\n\n"
            "If you wan delete everything, just talk \"delete my data\".\n\n"
            "Full details: {url}"
        ),
        "english": (
            "What I save: your phone number, sales, stock, expenses, customer names, and what you tell me by voice or text.\n\n"
            "Why: to help you track your shop.\n\n"
            "Who can see it: only you — through your phone or your report link.\n\n"
            "I don't sell or share your data with anyone.\n\n"
            "If you want to delete everything, just say \"delete my data\".\n\n"
            "Full details: {url}"
        ),
    },
    "delete_confirm": {
        "pidgin": (
            "You sure say you wan delete ALL your records? Sales, stock, credits, expenses — everything go disappear. "
            "This one no fit reverse o.\n\n"
            "Say \"yes\" to delete, or \"no\" to keep your data."
        ),
        "english": (
            "Are you sure you want to delete ALL your records? Sales, stock, credits, expenses — everything will be gone. "
            "This cannot be undone.\n\n"
            "Say \"yes\" to delete, or \"no\" to keep your data."
        ),
    },
    "delete_done": {
        "pidgin": "I don delete all your data. Your account don clear. If you send me message again, we go start fresh.",
        "english": "All your data has been deleted. Your account is cleared. If you message me again, we'll start fresh.",
    },
    "delete_cancelled": {
        "pidgin": "No wahala, your data still dey safe.",
        "english": "No problem, your data is safe.",
    },

    "hint_bulk_detail": {
        "pidgin": "Next time if you remember wetin you sell, list am — I go track each product for you.",
        "english": "Next time if you remember what you sold, list the items — I'll track each product for you.",
    },
    "hint_long_voice": {
        "pidgin": "\n\nNext time, try send shorter voice note so I no go miss anything.",
        "english": "\n\nNext time, try sending shorter voice notes so I don't miss anything.",
    },
    "long_voice_confirm": {
        "pidgin": "That voice note long. I hear everything correct? Say \"yes\" make I record am, or \"no\" make you send am again.",
        "english": "That was a long voice note. Did I get everything right? Say \"yes\" to record it, or \"no\" to try again.",
    },
    "welcome_voice_tip": {
        "pidgin": "I be Tijah, your shop helper. ",
        "english": "I'm Tijah, your shop helper. ",
    },
    "nudge_morning": {
        "pidgin": "Good morning! Ready to record today sales. Just yarn to me when you sell something.",
        "english": "Good morning! Ready to record today's sales. Just tell me when you sell something.",
    },
    "nudge_debt_aging": {
        "pidgin": "\n\n{customer} don owe you {amount} naira for {days} days now. Say \"remind {customer}\" make I write reminder for you.",
        "english": "\n\n{customer} has owed you {amount} naira for {days} days. Say \"remind {customer}\" and I'll write a reminder for you.",
    },
    "nudge_low_stock": {
        "pidgin": "\n\nStock dey low: {items}. Time to restock!",
        "english": "\n\nLow stock alert: {items}. Time to restock!",
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
    "hint_discover_check_sales": {
        "pidgin": "\n\nYou fit ask \"wetin I sell today?\" to see everything wey you don record.",
        "english": "\n\nYou can ask \"what did I sell today?\" to see everything you've recorded.",
    },
    "hint_discover_weekly": {
        "pidgin": "\n\nYou don dey record well! Try ask \"how my week go?\" or \"wetin happen this month?\" to see your progress.",
        "english": "\n\nYou're recording well! Try asking \"how was my week?\" or \"how was this month?\" to see your progress.",
    },
    "hint_try_voice": {
        "pidgin": "\n\nYou fit send voice note instead of typing! Just press the mic and yarn wetin you sell - e dey faster.",
        "english": "\n\nYou can send voice notes instead of typing! Just hold the mic and say what you sold - it's faster.",
    },
    "hint_shop_name": {
        "pidgin": "\n\nYou fit give your shop name! Just talk \"my shop name na Mama T Store\" - e go show for your report.",
        "english": "\n\nYou can name your shop! Just say \"my shop name is Mama T Store\" - it will show on your report.",
    },
    "nudge_top_seller": {
        "pidgin": "\n\nYour top seller today na {product} ({total} naira). Keep am stocked!",
        "english": "\n\nYour top seller today was {product} ({total} naira). Keep it stocked!",
    },

    # === PROACTIVE INSIGHTS ===
    "milestone_sales": {
        "pidgin": "\n\nYou don reach {count} sales! You dey do well, keep am up!",
        "english": "\n\nYou just hit {count} sales! You're doing great, keep it up!",
    },
    "milestone_revenue": {
        "pidgin": "\n\nYour shop don make over {amount} naira! Na big achievement!",
        "english": "\n\nYour shop has made over {amount} naira! That's a big achievement!",
    },
    "insight_best_day": {
        "pidgin": "\n\nYour best day na {day} ({total} naira).",
        "english": "\n\nYour busiest day was {day} ({total} naira).",
    },
    "insight_customer_concentration": {
        "pidgin": "\n\nYour top customer na {customer} ({total} naira — {pct}% of your sales).",
        "english": "\n\nYour top customer is {customer} ({total} naira — {pct}% of sales).",
    },
    "insight_margin_drop": {
        "pidgin": "\n\nYour profit margin don drop from {old_margin}% to {new_margin}% this month. Check your prices.",
        "english": "\n\nYour profit margin dropped from {old_margin}% to {new_margin}% this month. Check your prices.",
    },
    "nudge_debt_30": {
        "pidgin": "\n\n{customer} don owe you {amount} naira for {days} days now. Try ask for part payment.",
        "english": "\n\n{customer} has owed you {amount} naira for {days} days. Consider asking for a partial payment.",
    },
    "nudge_debt_60": {
        "pidgin": "\n\n{customer} don owe you {amount} naira for {days} days! This debt don old o. Try go visit am.",
        "english": "\n\n{customer} has owed you {amount} naira for {days} days! This debt is getting old. You may want to visit them.",
    },
    "nudge_slow_product": {
        "pidgin": "\n\nYou never sell {product} for {days} days now. Think about whether to reduce how much you buy.",
        "english": "\n\nYou haven't sold {product} in {days} days. Consider buying less next time.",
    },
    "nudge_restock": {
        "pidgin": "\n\n{product} don finish but e dey sell well. Time to restock!",
        "english": "\n\n{product} is out of stock but sells well. Time to restock!",
    },
    "nudge_weekly_up": {
        "pidgin": (
            "Your week don end! This week: {this_total} naira ({this_count} sales). "
            "Last week: {last_total} naira. You dey grow! Well done!"
        ),
        "english": (
            "Your week is done! This week: {this_total} naira ({this_count} sales). "
            "Last week: {last_total} naira. You're growing! Well done!"
        ),
    },
    "nudge_weekly_down": {
        "pidgin": (
            "Your week don end! This week: {this_total} naira ({this_count} sales). "
            "Last week: {last_total} naira. Next week go better!"
        ),
        "english": (
            "Your week is done! This week: {this_total} naira ({this_count} sales). "
            "Last week: {last_total} naira. Next week will be better!"
        ),
    },
    "nudge_weekly_first": {
        "pidgin": "Your week don end! This week: {this_total} naira ({this_count} sales). Well done!",
        "english": "Your week is done! This week: {this_total} naira ({this_count} sales). Well done!",
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
