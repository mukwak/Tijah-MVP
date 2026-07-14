"""Business logic handlers for each intent."""
import json
from datetime import datetime, timedelta
from app.database import get_db
from app.responses import get_response


def _fmt(num: float) -> str:
    """Format number with commas: 15000 -> 15,000"""
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"


def _resolve_when(when: str) -> str | None:
    """Convert 'yesterday', '-2' etc. to a WAT datetime string. None = now (use DB default)."""
    if not when or when == "today":
        return None
    # UTC+1 for Nigeria (WAT)
    now_wat = datetime.utcnow() + timedelta(hours=1)
    if when == "yesterday":
        dt = now_wat - timedelta(days=1)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        days = int(when)
        dt = now_wat + timedelta(days=days)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def handle_record_sale(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity", 1))
    unit = data.get("unit") or "piece"
    total = float(data.get("total", 0))
    unit_price = float(data.get("unit_price", 0))
    customer = data.get("customer")
    is_credit = data.get("is_credit", False)

    # Always recalculate — never trust LLM math
    if unit_price and quantity:
        total = unit_price * quantity
    elif total and quantity and not unit_price:
        unit_price = total / quantity
    elif total and not unit_price:
        unit_price = total

    # If no price given, try to use stored sell_price
    if not total and not unit_price:
        existing = await _find_product(db, phone, product)
        if existing and existing[2] > 0:
            unit_price = existing[2]
            total = unit_price * quantity
        else:
            return get_response("sale_needs_price", lang, product=product)

    # Find or create product
    product_id = await _get_or_create_product(db, phone, product, unit, unit_price)

    # Deduct stock. Allow negative stock so oversells are visible instead of hidden.
    await db.execute(
        "UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?",
        (quantity, product_id),
    )

    # Record sale (with optional backdating)
    when = _resolve_when(data.get("when", "today"))
    if when:
        await db.execute(
            """INSERT INTO sales (phone, product_id, product_name, quantity, unit_price, total, customer, is_credit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (phone, product_id, product, quantity, unit_price, total, customer, 1 if is_credit else 0, when),
        )
    else:
        await db.execute(
            """INSERT INTO sales (phone, product_id, product_name, quantity, unit_price, total, customer, is_credit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (phone, product_id, product, quantity, unit_price, total, customer, 1 if is_credit else 0),
        )

    # If credit sale, also record in credits
    if is_credit and customer:
        await _add_credit(db, phone, customer, total, f"{_fmt(quantity)} {unit} of {product}")

    await db.commit()

    credit_note = ""
    if is_credit and customer:
        if lang == "pidgin":
            credit_note = f"\n{customer} buy am on credit."
        else:
            credit_note = f"\n{customer} bought on credit."

    # Stock warnings only make sense if the user actually tracks stock for this product
    has_stock_data = (await (await db.execute(
        "SELECT COUNT(*) FROM stock_entries WHERE phone = ? AND product_id = ?",
        (phone, product_id),
    )).fetchone())[0] > 0

    low_stock_msg = ""
    if has_stock_data:
        cursor = await db.execute(
            "SELECT stock_qty, unit FROM products WHERE id = ?", (product_id,)
        )
        row = await cursor.fetchone()
        if row and row[0] < 0:
            low_stock_msg = "\n" + get_response(
                "stock_oversold", lang, product=product, quantity=_fmt(abs(row[0])), unit=row[1]
            )
        elif row and row[0] == 0:
            low_stock_msg = "\n" + get_response("stock_finished", lang, product=product)
        elif row and row[0] <= 3:
            low_stock_msg = "\n" + get_response("stock_low", lang, product=product, quantity=_fmt(row[0]), unit=row[1])

    result = get_response(
        "sale_recorded", lang,
        quantity=_fmt(quantity), unit=unit, product=product, total=_fmt(total),
        credit_note=credit_note,
    ) + low_stock_msg

    # One contextual nudge — the natural next step for this action
    if not has_stock_data:
        # First couple of sales of an untracked product: offer stock tracking
        product_sales = (await (await db.execute(
            "SELECT COUNT(*) FROM sales WHERE phone = ? AND product_id = ?",
            (phone, product_id),
        )).fetchone())[0]
        if product_sales <= 2:
            result += get_response("hint_stock_unknown", lang, product=product)
    else:
        # Rotate one discovery hint over the first few sales
        sale_count = (await (await db.execute(
            "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
        )).fetchone())[0]
        if sale_count == 1:
            result += get_response("hint_after_sale", lang)
        elif sale_count == 2:
            result += get_response("hint_undo", lang)
        elif sale_count == 3:
            result += get_response("hint_after_expense", lang)

    return result


async def handle_add_stock(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity", 1))
    unit = data.get("unit") or "piece"
    cost_price = float(data.get("cost_price", 0))

    product_id = await _get_or_create_product(db, phone, product, unit, 0, cost_price)

    # Update stock
    await db.execute(
        "UPDATE products SET stock_qty = stock_qty + ?, cost_price = CASE WHEN ? > 0 THEN ? ELSE cost_price END WHERE id = ?",
        (quantity, cost_price, cost_price, product_id),
    )

    # Record entry
    await db.execute(
        """INSERT INTO stock_entries (phone, product_id, product_name, quantity, cost_price, entry_type)
           VALUES (?, ?, ?, ?, ?, 'purchase')""",
        (phone, product_id, product, quantity, cost_price),
    )
    await db.commit()

    price_note = ""
    if cost_price > 0:
        total_cost = cost_price * quantity
        price_note = f" Cost: {_fmt(total_cost)} naira ({_fmt(cost_price)} each)."

    result = get_response(
        "stock_added", lang,
        quantity=_fmt(quantity), unit=unit, product=product, price_note=price_note,
    )

    # One contextual nudge — if no selling price is set, that's the natural next step
    sell_price = (await (await db.execute(
        "SELECT sell_price FROM products WHERE id = ?", (product_id,)
    )).fetchone())[0]
    product_entries = (await (await db.execute(
        "SELECT COUNT(*) FROM stock_entries WHERE phone = ? AND product_id = ?",
        (phone, product_id),
    )).fetchone())[0]
    if not sell_price and product_entries <= 2:
        result += get_response("hint_set_price", lang, product=product, unit=unit)
    else:
        stock_count = (await (await db.execute(
            "SELECT COUNT(*) FROM stock_entries WHERE phone = ?", (phone,)
        )).fetchone())[0]
        if stock_count <= 2:
            result += get_response("hint_after_stock", lang)

    return result


async def handle_record_credit(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    customer = data.get("customer", "Customer")
    amount = float(data.get("amount", 0))
    note = data.get("note", "")

    # Check for similar existing customer unless a pending confirmation already resolved it.
    matched_name, match_type = (customer, None)
    if not data.get("_skip_customer_match"):
        matched_name, match_type = await _find_similar_customer(db, phone, customer)

    if match_type == "fuzzy":
        # Save pending and ask for confirmation
        data["_confirmed_customer"] = matched_name
        data["_original_customer"] = customer
        await _save_pending(db, phone, {"action": "record_credit", "data": data, "lang": lang})
        return get_response("confirm_customer", lang, original=customer, matched=matched_name)

    if match_type == "exact":
        customer = matched_name

    await _add_credit(db, phone, customer, amount, note)
    await db.commit()

    note_text = f" ({note})" if note else ""
    result = get_response(
        "credit_recorded", lang,
        customer=customer, amount=_fmt(amount), note=note_text,
    )

    # Drip hint for new users
    credit_count = (await (await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if credit_count <= 2:
        result += get_response("hint_after_credit", lang, customer=customer)

    return result


async def handle_record_payment(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    customer = data.get("customer", "Customer")
    amount = float(data.get("amount", 0))

    # Check for similar existing customer unless a pending confirmation already resolved it.
    matched_name, match_type = (customer, None)
    if not data.get("_skip_customer_match"):
        matched_name, match_type = await _find_similar_customer(db, phone, customer)

    if match_type == "fuzzy":
        data["_confirmed_customer"] = matched_name
        data["_original_customer"] = customer
        await _save_pending(db, phone, {"action": "record_payment", "data": data, "lang": lang})
        return get_response("confirm_customer", lang, original=customer, matched=matched_name)

    if match_type == "exact":
        customer = matched_name

    # Find unsettled credits for this customer
    cursor = await db.execute(
        """SELECT id, amount, paid FROM credits
           WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    rows = await cursor.fetchall()

    if not rows:
        return get_response("customer_not_found", lang, customer=customer)

    # Log the payment in the payments table (audit trail)
    await db.execute(
        "INSERT INTO payments (phone, customer, amount) VALUES (?, ?, ?)",
        (phone, customer, amount),
    )

    # Apply payment to credits (FIFO)
    remaining_payment = amount
    for row in rows:
        credit_id, credit_amount, already_paid = row[0], row[1], row[2]
        outstanding = credit_amount - already_paid
        if remaining_payment >= outstanding:
            await db.execute(
                "UPDATE credits SET paid = amount, settled = 1, updated_at = datetime('now', '+1 hours') WHERE id = ?",
                (credit_id,),
            )
            remaining_payment -= outstanding
        else:
            await db.execute(
                "UPDATE credits SET paid = paid + ?, updated_at = datetime('now', '+1 hours') WHERE id = ?",
                (remaining_payment, credit_id),
            )
            remaining_payment = 0
            break

    await db.commit()

    # Check remaining debt
    cursor = await db.execute(
        """SELECT SUM(amount - paid) FROM credits
           WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0""",
        (phone, customer),
    )
    row = await cursor.fetchone()
    remaining = row[0] if row and row[0] else 0

    if remaining > 0:
        remaining_note = get_response("remaining_debt", lang, remaining=_fmt(remaining))
    else:
        remaining_note = get_response("debt_cleared", lang, customer=customer)

    return get_response(
        "payment_recorded", lang,
        customer=customer, amount=_fmt(amount), remaining_note=remaining_note,
    )


async def handle_check_stock(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product")

    if product:
        found = await _find_product(db, phone, product)
        if found:
            cursor = await db.execute(
                "SELECT stock_qty, unit FROM products WHERE id = ?",
                (found[0],),
            )
            row = await cursor.fetchone()
        else:
            row = None
        if row:
            return get_response(
                "stock_check_single", lang,
                quantity=_fmt(row[0]), unit=row[1], product=product,
            )
        return get_response("stock_empty", lang)

    cursor = await db.execute(
        "SELECT name, stock_qty, unit, sell_price FROM products WHERE phone = ? ORDER BY name",
        (phone,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return get_response("stock_empty", lang)

    stock_list = "\n".join(
        f"  {row[0]}: {_fmt(row[1])} {row[2]}" + (f" @ {_fmt(row[3])} ea" if row[3] else "")
        for row in rows
    )
    return get_response(
        "stock_check_all", lang,
        stock_list=stock_list, count=len(rows),
    )


async def handle_check_credits(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    customer = data.get("customer")

    if customer:
        cursor = await db.execute(
            """SELECT amount, paid, note, created_at FROM credits
               WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0
               ORDER BY created_at DESC""",
            (phone, customer),
        )
    else:
        cursor = await db.execute(
            """SELECT MIN(customer) as customer, SUM(amount - paid) as owed FROM credits
               WHERE phone = ? AND settled = 0
               GROUP BY LOWER(customer)
               ORDER BY owed DESC""",
            (phone,),
        )

    rows = await cursor.fetchall()
    if not rows:
        return get_response("credits_empty", lang)

    if customer:
        total = sum(r[0] - r[1] for r in rows)
        credit_list = "\n".join(
            f"  {_fmt(r[0] - r[1])} naira" + (f" - {r[2]}" if r[2] else "")
            for r in rows
        )
        return get_response(
            "credits_list", lang,
            credit_list=f"  {customer}:\n{credit_list}",
            total=_fmt(total),
        )

    total = sum(r[1] for r in rows)
    credit_list = "\n".join(f"  {r[0]}: {_fmt(r[1])} naira" for r in rows)
    result = get_response(
        "credits_list", lang,
        credit_list=credit_list, total=_fmt(total),
    )
    # Natural next step: offer a reminder message for the biggest debtor
    result += get_response("hint_credit_reminder", lang, customer=rows[0][0])
    return result


async def handle_record_expense(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    description = data.get("description", "expense")
    amount = float(data.get("amount", 0))
    category = data.get("category", "other")

    await db.execute(
        "INSERT INTO expenses (phone, description, amount, category) VALUES (?, ?, ?, ?)",
        (phone, description, amount, category),
    )
    await db.commit()

    result = get_response(
        "expense_recorded", lang,
        amount=_fmt(amount), description=description,
    )

    # First expenses: point to the daily summary as the natural next step
    expense_count = (await (await db.execute(
        "SELECT COUNT(*) FROM expenses WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if expense_count <= 2:
        result += get_response("hint_after_expense", lang)

    return result


async def handle_check_expenses(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    period = data.get("period", "today")

    if period == "today":
        date_filter = "date(created_at) = date('now', '+1 hours')"
        period_text = "today" if lang == "english" else "today"
    elif period == "week":
        date_filter = "created_at >= datetime('now', '+1 hours', '-7 days')"
        period_text = "this week" if lang == "english" else "this week"
    else:
        date_filter = "created_at >= datetime('now', '+1 hours', '-30 days')"
        period_text = "this month" if lang == "english" else "this month"

    cursor = await db.execute(
        f"""SELECT description, amount, category FROM expenses
           WHERE phone = ? AND {date_filter}
           ORDER BY created_at DESC""",
        (phone,),
    )
    rows = await cursor.fetchall()

    if not rows:
        return get_response("expenses_empty", lang, period=period_text)

    total = sum(r[1] for r in rows)
    expense_list = "\n".join(
        f"  {r[0]}: {_fmt(r[1])} naira"
        for r in rows
    )
    return get_response(
        "expenses_list", lang,
        period=period_text, expense_list=expense_list, total=_fmt(total),
    )


async def handle_check_sales(phone: str, data: dict, lang: str) -> str:
    """Show individual sales for a period."""
    db = await get_db()
    period = data.get("period", "today")

    if period == "today":
        date_filter = "date(created_at) = date('now', '+1 hours')"
        period_text = "today"
    elif period == "yesterday":
        date_filter = "date(created_at) = date('now', '+1 hours', '-1 day')"
        period_text = "yesterday"
    elif period == "week":
        date_filter = "created_at >= datetime('now', '+1 hours', '-7 days')"
        period_text = "this week"
    else:
        date_filter = "created_at >= datetime('now', '+1 hours', '-30 days')"
        period_text = "this month"

    cursor = await db.execute(
        f"""SELECT product_name, quantity, unit_price, total, created_at
           FROM sales WHERE phone = ? AND {date_filter}
           ORDER BY created_at DESC""",
        (phone,),
    )
    rows = await cursor.fetchall()

    if not rows:
        if lang == "pidgin":
            return f"You never sell anything {period_text}."
        return f"No sales {period_text}."

    total = sum(r[3] for r in rows)
    sales_lines = []
    for r in rows:
        time_str = r[4][11:16] if r[4] and len(r[4]) > 15 else ""
        line = f"  {r[0]} x{_fmt(r[1])} = {_fmt(r[3])} naira"
        if time_str:
            line += f"  ({time_str})"
        sales_lines.append(line)

    sales_list = "\n".join(sales_lines)

    if lang == "pidgin":
        return f"Wetin you sell {period_text}:\n{sales_list}\n\nTotal: {_fmt(total)} naira ({len(rows)} sales)"
    return f"Your sales {period_text}:\n{sales_list}\n\nTotal: {_fmt(total)} naira ({len(rows)} sales)"


async def handle_daily_summary(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    period = data.get("period", "today")

    if period == "today":
        date_filter = "date(created_at) = date('now', '+1 hours')"
        period_label = "Today" if lang == "english" else "Today"
    elif period == "yesterday":
        date_filter = "date(created_at) = date('now', '+1 hours', '-1 day')"
        period_label = "Yesterday" if lang == "english" else "Yesterday"
    elif period == "week":
        date_filter = "created_at >= datetime('now', '+1 hours', '-7 days')"
        period_label = "This week" if lang == "english" else "This week"
    else:
        date_filter = "created_at >= datetime('now', '+1 hours', '-30 days')"
        period_label = "This month" if lang == "english" else "This month"

    # Sales
    cursor = await db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND {date_filter}",
        (phone,),
    )
    row = await cursor.fetchone()
    sales_count, sales_total = row[0], row[1]

    # Expenses
    cursor = await db.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE phone = ? AND {date_filter}",
        (phone,),
    )
    expense_total = (await cursor.fetchone())[0]

    # Credits given
    cursor = await db.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM credits WHERE phone = ? AND {date_filter}",
        (phone,),
    )
    credit_total = (await cursor.fetchone())[0]

    # Payments received
    cursor = await db.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM payments WHERE phone = ? AND {date_filter}",
        (phone,),
    )
    payment_total = (await cursor.fetchone())[0]

    if sales_count == 0 and expense_total == 0 and credit_total == 0 and payment_total == 0:
        return get_response("no_activity", lang)

    net_cash = sales_total - credit_total + payment_total - expense_total

    # Build summary progressively — only show what's relevant
    if expense_total > 0:
        result = get_response(
            "daily_summary_with_expenses", lang,
            period=period_label,
            sales_count=sales_count,
            sales_total=_fmt(sales_total),
            expense_total=_fmt(expense_total),
            net_cash=_fmt(net_cash),
        )
    else:
        result = get_response(
            "daily_summary_simple", lang,
            period=period_label,
            sales_count=sales_count,
            sales_total=_fmt(sales_total),
        )

    if credit_total > 0:
        result += get_response("daily_summary_credits_line", lang, credit_total=_fmt(credit_total))

    if payment_total > 0:
        result += get_response("daily_summary_payments_line", lang, payment_total=_fmt(payment_total))

    # Top products (only if more than 1 product sold)
    cursor = await db.execute(
        f"""SELECT product_name, SUM(quantity), SUM(total) FROM sales
           WHERE phone = ? AND {date_filter}
           GROUP BY product_name ORDER BY SUM(total) DESC LIMIT 3""",
        (phone,),
    )
    top = await cursor.fetchall()
    if len(top) > 1:
        top_products = "\n".join(
            f"  {r[0]}: {_fmt(r[1])} sold = {_fmt(r[2])} naira" for r in top
        )
        result += get_response("daily_summary_top", lang, top_products=top_products)

    # Simple insight: compare with the previous period
    prev_filters = {
        "today": ("date(created_at) = date('now', '+1 hours', '-1 day')", "Yesterday"),
        "week": (
            "created_at >= datetime('now', '+1 hours', '-14 days') "
            "AND created_at < datetime('now', '+1 hours', '-7 days')",
            "Last week",
        ),
        "month": (
            "created_at >= datetime('now', '+1 hours', '-60 days') "
            "AND created_at < datetime('now', '+1 hours', '-30 days')",
            "Last month",
        ),
    }
    if period in prev_filters and sales_total > 0:
        prev_filter, prev_label = prev_filters[period]
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND {prev_filter}",
            (phone,),
        )
        prev_total = (await cursor.fetchone())[0]
        if prev_total > 0:
            key = "insight_better" if sales_total > prev_total else "insight_less"
            result += get_response(key, lang, prev_label=prev_label, prev_total=_fmt(prev_total))

    # If the user has never opened their report, point them to it once per summary
    token_row = await (await db.execute(
        "SELECT token FROM report_tokens WHERE phone = ?", (phone,)
    )).fetchone()
    if not token_row:
        result += get_response("hint_report", lang)

    return result


async def handle_set_price(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    unit = data.get("unit") or "piece"
    sell_price = float(data.get("sell_price", 0))

    product_id = await _get_or_create_product(db, phone, product, unit, sell_price)
    await db.execute(
        "UPDATE products SET sell_price = ? WHERE id = ?",
        (sell_price, product_id),
    )
    await db.commit()

    return get_response(
        "price_set", lang,
        product=product, price=_fmt(sell_price), unit=unit,
    )


async def handle_change_language(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    new_lang = data.get("language", "english").lower()
    if new_lang not in ("pidgin", "english"):
        new_lang = "english"

    await db.execute("UPDATE shops SET language = ? WHERE phone = ?", (new_lang, phone))
    await db.commit()

    return get_response("language_changed", new_lang)


async def handle_get_report(phone: str, data: dict, lang: str) -> str:
    """Send the shop's private shareable report link."""
    from app.config import BASE_URL
    from app.report import get_or_create_report_token

    token = await get_or_create_report_token(phone)
    url = f"{BASE_URL.rstrip('/')}/report/{token}"
    result = get_response("report_link", lang, url=url)

    # No shop name yet? The natural next step is to put one on the report.
    db = await get_db()
    row = await (await db.execute(
        "SELECT name FROM shops WHERE phone = ?", (phone,)
    )).fetchone()
    if not (row and row[0]):
        result += get_response("shop_name_ask", lang)
    return result


async def handle_set_shop_name(phone: str, data: dict, lang: str) -> str:
    """Save the shop's name so it shows on the report."""
    name = (data.get("name") or "").strip()
    if not name:
        if lang == "pidgin":
            return "Wetin be the shop name? Tell me like \"my shop name na Mama T Store\"."
        return "What is the shop name? Tell me like \"my shop name is Mama T Store\"."

    db = await get_db()
    await db.execute("UPDATE shops SET name = ? WHERE phone = ?", (name, phone))
    await db.commit()
    return get_response("shop_name_set", lang, name=name)


async def handle_feedback(phone: str, data: dict, lang: str) -> str:
    """Store tester feedback/complaints so the team can review them."""
    db = await get_db()
    message = (data.get("message") or "").strip()

    if not message:
        if lang == "pidgin":
            return "Wetin happen? Tell me the problem, I go send am to the Tijah team."
        return "What happened? Tell me the problem and I'll send it to the Tijah team."

    await db.execute(
        "INSERT INTO feedback (phone, message) VALUES (?, ?)",
        (phone, message),
    )
    await db.commit()
    return get_response("feedback_saved", lang)


async def handle_credit_history(phone: str, data: dict, lang: str) -> str:
    """Show full credit and payment history for a customer."""
    db = await get_db()
    customer = data.get("customer", "")

    if not customer:
        if lang == "pidgin":
            return "Who you wan check? Tell me the name."
        return "Which customer? Tell me the name."

    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type:
        customer = matched

    # Get all credits
    cursor = await db.execute(
        """SELECT amount, paid, note, created_at, settled FROM credits
           WHERE phone = ? AND LOWER(customer) = LOWER(?)
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    credits = await cursor.fetchall()

    # Get all payments
    cursor = await db.execute(
        """SELECT amount, created_at FROM payments
           WHERE phone = ? AND LOWER(customer) = LOWER(?)
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    payments = await cursor.fetchall()

    if not credits and not payments:
        return get_response("customer_not_found", lang, customer=customer)

    lines = []

    if credits:
        if lang == "pidgin":
            lines.append(f"Credit wey {customer} take:")
        else:
            lines.append(f"Credits for {customer}:")
        for c in credits:
            date = c[3][:10] if c[3] else ""
            note = f" - {c[2]}" if c[2] else ""
            status = " (paid)" if c[4] else f" (owing {_fmt(c[0] - c[1])})"
            lines.append(f"  {_fmt(c[0])} naira{note} [{date}]{status}")

    if payments:
        lines.append("")
        if lang == "pidgin":
            lines.append("Wetin e don pay:")
        else:
            lines.append("Payments made:")
        for p in payments:
            date = p[1][:10] if p[1] else ""
            lines.append(f"  {_fmt(p[0])} naira [{date}]")

    # Total outstanding
    total_owed = sum(c[0] - c[1] for c in credits if not c[4])
    total_paid = sum(p[0] for p in payments)
    lines.append("")
    if lang == "pidgin":
        lines.append(f"Total wey e don pay: {_fmt(total_paid)} naira")
        lines.append(f"E still owe: {_fmt(total_owed)} naira")
    else:
        lines.append(f"Total paid: {_fmt(total_paid)} naira")
        lines.append(f"Still owing: {_fmt(total_owed)} naira")

    return "\n".join(lines)


async def handle_edit_credit(phone: str, data: dict, lang: str) -> str:
    """Correct a credit amount for a customer."""
    db = await get_db()
    customer = data.get("customer", "")
    new_amount = float(data.get("new_amount", 0))

    if not customer or not new_amount:
        if lang == "pidgin":
            return "Tell me the name and correct amount. Like: \"Mama Joy owes 5 thousand not 8\""
        return "Tell me the name and correct amount. Like: \"Mama Joy owes 5 thousand not 8\""

    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type:
        customer = matched

    old_amount = float(data.get("old_amount", 0))

    # If old_amount is given, find that specific credit; otherwise find most recent
    if old_amount:
        cursor = await db.execute(
            """SELECT id, amount FROM credits
               WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0 AND amount = ?
               ORDER BY created_at DESC LIMIT 1""",
            (phone, customer, old_amount),
        )
    else:
        cursor = await db.execute(
            """SELECT id, amount FROM credits
               WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0
               ORDER BY created_at DESC LIMIT 1""",
            (phone, customer),
        )
    row = await cursor.fetchone()

    if not row:
        return get_response("customer_not_found", lang, customer=customer)

    old_amount = row[1]
    await db.execute(
        "UPDATE credits SET amount = ?, updated_at = datetime('now', '+1 hours') WHERE id = ?",
        (new_amount, row[0]),
    )
    await db.commit()

    if lang == "pidgin":
        return f"I don change {customer} credit from {_fmt(old_amount)} to {_fmt(new_amount)} naira."
    return f"Updated {customer}'s credit from {_fmt(old_amount)} to {_fmt(new_amount)} naira."


async def handle_credit_reminder(phone: str, data: dict, lang: str) -> str:
    """Generate a shareable/forwardable credit reminder for a customer."""
    db = await get_db()
    customer = data.get("customer", "")

    if not customer:
        if lang == "pidgin":
            return "Who you wan remind? Tell me like: \"remind Mama Joy\""
        return "Who do you want to remind? Tell me like: \"remind Mama Joy\""

    # Normalize customer name
    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type:
        customer = matched

    cursor = await db.execute(
        """SELECT amount, paid, note, created_at FROM credits
           WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    rows = await cursor.fetchall()

    if not rows:
        return get_response("customer_not_found", lang, customer=customer)

    total = sum(r[0] - r[1] for r in rows)

    # Get shop name for the reminder
    cursor = await db.execute("SELECT name FROM shops WHERE phone = ?", (phone,))
    shop_row = await cursor.fetchone()
    shop_name = shop_row[0] if shop_row and shop_row[0] else "our shop"

    # Build a clean, forwardable message
    items = []
    for r in rows:
        owed = r[0] - r[1]
        date = r[3][:10] if r[3] else ""
        note = r[2] if r[2] else ""
        line = f"  {_fmt(owed)} naira"
        if note:
            line += f" - {note}"
        if date:
            line += f" ({date})"
        items.append(line)

    items_str = "\n".join(items)

    if lang == "pidgin":
        reminder = (
            f"Hello {customer},\n\n"
            f"This na friendly reminder from {shop_name}.\n"
            f"You still owe us {_fmt(total)} naira:\n\n"
            f"{items_str}\n\n"
            f"Abeg make payment when you fit. Thank you!"
        )
    else:
        reminder = (
            f"Hello {customer},\n\n"
            f"This is a friendly reminder from {shop_name}.\n"
            f"You still owe {_fmt(total)} naira:\n\n"
            f"{items_str}\n\n"
            f"Please make payment when you can. Thank you!"
        )

    prefix = "Forward this message to " + customer + ":\n\n" if lang == "english" else "Send this message give " + customer + ":\n\n"
    return prefix + reminder


async def handle_confirm_yes(phone: str, data: dict, lang: str) -> str:
    """User confirmed the fuzzy customer match."""
    db = await get_db()
    pending = await _get_pending(db, phone)
    if not pending:
        if lang == "pidgin":
            return "Nothing to confirm. Just tell me wetin you wan do."
        return "Nothing to confirm. Just tell me what you need."

    # Use the confirmed (matched) customer name
    pending_data = pending["data"]
    pending_data["customer"] = pending_data.pop("_confirmed_customer")
    pending_data.pop("_original_customer", None)
    pending_data["_skip_customer_match"] = True
    pending_lang = pending.get("lang", lang)

    if pending["action"] == "record_credit":
        return await handle_record_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "record_payment":
        return await handle_record_payment(phone, pending_data, pending_lang)

    return get_response("error", lang)


async def handle_confirm_no(phone: str, data: dict, lang: str) -> str:
    """User rejected the fuzzy match — use original name as new customer."""
    db = await get_db()
    pending = await _get_pending(db, phone)
    if not pending:
        if lang == "pidgin":
            return "Nothing to confirm. Just tell me wetin you wan do."
        return "Nothing to confirm. Just tell me what you need."

    # Use the original (new) customer name
    pending_data = pending["data"]
    pending_data["customer"] = pending_data.pop("_original_customer")
    pending_data.pop("_confirmed_customer", None)
    pending_data["_skip_customer_match"] = True
    pending_lang = pending.get("lang", lang)

    if pending["action"] == "record_credit":
        return await handle_record_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "record_payment":
        return await handle_record_payment(phone, pending_data, pending_lang)

    return get_response("error", lang)


async def handle_rename_customer(phone: str, data: dict, lang: str) -> str:
    """Rename a customer across all credit records."""
    db = await get_db()
    old_name = data.get("old_name", "")
    new_name = data.get("new_name", "")

    if not old_name or not new_name:
        if lang == "pidgin":
            return "Tell me like: \"Change Mama Inkechi to Mama Nkechi\""
        return "Tell me like: \"Change Mama Inkechi to Mama Nkechi\""

    # Find the existing customer (fuzzy match on old name)
    matched, match_type = await _find_similar_customer(db, phone, old_name)
    if match_type:
        old_name = matched

    cursor = await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ? AND LOWER(customer) = LOWER(?)",
        (phone, old_name),
    )
    count = (await cursor.fetchone())[0]

    if count == 0:
        return get_response("customer_not_found", lang, customer=old_name)

    await db.execute(
        "UPDATE credits SET customer = ? WHERE phone = ? AND LOWER(customer) = LOWER(?)",
        (new_name, phone, old_name),
    )
    await db.commit()

    if lang == "pidgin":
        return f"I don change \"{old_name}\" to \"{new_name}\" for all {count} record(s)."
    return f"Changed \"{old_name}\" to \"{new_name}\" across {count} record(s)."


async def handle_edit_last(phone: str, data: dict, lang: str) -> str:
    """Edit the last recorded sale (change quantity, price, etc.)."""
    db = await get_db()
    field = data.get("field", "")
    new_value = data.get("new_value")

    if not field or new_value is None:
        if lang == "pidgin":
            return "Wetin you wan change? Tell me like: \"change to 3 bags\" or \"the price was 5 thousand\""
        return "What do you want to change? Tell me like: \"change to 3 bags\" or \"the price was 5 thousand\""

    # Get the last sale
    cursor = await db.execute(
        "SELECT id, product_name, quantity, unit_price, total, product_id FROM sales WHERE phone = ? ORDER BY created_at DESC LIMIT 1",
        (phone,),
    )
    row = await cursor.fetchone()
    if not row:
        if lang == "pidgin":
            return "I no see any sale to change."
        return "No sale to edit."

    sale_id, product_name, old_qty, old_price, old_total, product_id = row[0], row[1], row[2], row[3], row[4], row[5]
    new_qty, new_price, new_total = old_qty, old_price, old_total

    new_value = float(new_value)

    if field in ("quantity", "qty"):
        new_qty = new_value
        new_total = new_qty * new_price
        # Fix stock: restore old qty, deduct new qty
        if product_id:
            stock_diff = old_qty - new_qty
            await db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (stock_diff, product_id))
    elif field in ("price", "unit_price"):
        new_price = new_value
        new_total = new_qty * new_price
    elif field == "total":
        new_total = new_value
        if new_qty > 0:
            new_price = new_total / new_qty

    await db.execute(
        "UPDATE sales SET quantity = ?, unit_price = ?, total = ? WHERE id = ?",
        (new_qty, new_price, new_total, sale_id),
    )
    await db.commit()

    if lang == "pidgin":
        return f"I don change am. {product_name}: {_fmt(new_qty)} x {_fmt(new_price)} = {_fmt(new_total)} naira."
    return f"Updated. {product_name}: {_fmt(new_qty)} x {_fmt(new_price)} = {_fmt(new_total)} naira."


async def handle_undo(phone: str, data: dict, lang: str) -> str:
    """Undo the last recorded action (sale, expense, credit, or stock entry)."""
    db = await get_db()

    # Find the most recent action across all tables
    tables = [
        ("sales", "product_name", "total", "quantity", "product_id"),
        ("expenses", "description", "amount", None, None),
        ("credits", "customer", "amount", None, None),
        ("payments", "customer", "amount", None, None),
        ("stock_entries", "product_name", "cost_price", "quantity", "product_id"),
    ]

    latest = None
    latest_table = None
    latest_qty_col = None
    latest_pid_col = None

    for table, desc_col, amount_col, qty_col, pid_col in tables:
        cursor = await db.execute(
            f"SELECT id, {desc_col}, {amount_col}, created_at"
            + (f", {qty_col}, {pid_col}" if qty_col else "")
            + f" FROM {table} WHERE phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )
        row = await cursor.fetchone()
        if row:
            if latest is None or row[3] > latest[3]:
                latest = row
                latest_table = table
                latest_qty_col = qty_col
                latest_pid_col = pid_col

    if not latest:
        if lang == "pidgin":
            return "Nothing to undo. You never record anything yet."
        return "Nothing to undo. You haven't recorded anything yet."

    desc = latest[1]
    amount = _fmt(latest[2]) if latest[2] else ""

    # Restore related data when undoing
    if latest_table == "sales" and latest_qty_col:
        qty = latest[4]
        pid = latest[5]
        if pid:
            await db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (qty, pid))
    elif latest_table == "stock_entries" and latest_qty_col:
        qty = latest[4]
        pid = latest[5]
        if pid:
            await db.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?", (qty, pid))
    elif latest_table == "payments":
        # Reverse the payment: reduce paid amounts on credits (LIFO - most recent first)
        pay_customer = latest[1]
        pay_amount = latest[2]
        remaining_refund = pay_amount

        # First unsettled credits that were partially paid
        cursor = await db.execute(
            """SELECT id, amount, paid FROM credits
               WHERE phone = ? AND LOWER(customer) = LOWER(?) AND paid > 0
               ORDER BY updated_at DESC""",
            (phone, pay_customer),
        )
        credit_rows = await cursor.fetchall()
        for cr in credit_rows:
            if remaining_refund <= 0:
                break
            cr_id, cr_amount, cr_paid = cr[0], cr[1], cr[2]
            refund = min(remaining_refund, cr_paid)
            new_paid = cr_paid - refund
            settled = 0 if new_paid < cr_amount else 1
            await db.execute(
                "UPDATE credits SET paid = ?, settled = ?, updated_at = datetime('now', '+1 hours') WHERE id = ?",
                (new_paid, settled, cr_id),
            )
            remaining_refund -= refund

    # Delete the record
    await db.execute(f"DELETE FROM {latest_table} WHERE id = ?", (latest[0],))
    await db.commit()

    # Build human-readable description
    labels = {"sales": "sale", "expenses": "expense", "credits": "credit", "payments": "payment", "stock_entries": "stock"}
    label = labels.get(latest_table, "record")

    if lang == "pidgin":
        return f"I don remove the last {label}: {desc} ({amount} naira)"
    return f"Removed last {label}: {desc} ({amount} naira)"


async def handle_multi_sale(phone: str, data: dict, lang: str) -> str:
    """Handle multiple products sold in one message."""
    items = data.get("items", [])
    if not items:
        return get_response("not_understood", lang)

    results = []
    grand_total = 0

    for item in items:
        # Process each item as a sale
        item["action"] = "record_sale"
        if "when" not in item and "when" in data:
            item["when"] = data["when"]
        result = await handle_record_sale(phone, item, lang)
        # Extract just the first line (the confirmation)
        first_line = result.split("\n")[0]
        results.append(first_line)
        # Recalculate — don't trust LLM total
        qty = float(item.get("quantity", 1))
        price = float(item.get("unit_price", 0))
        grand_total += qty * price

    summary = "\n".join(results)
    if lang == "pidgin":
        summary += f"\n\nTotal: {_fmt(grand_total)} naira for everything."
    else:
        summary += f"\n\nTotal: {_fmt(grand_total)} naira for all items."

    return summary


# ---- Helpers ----

async def _find_product(db, phone, name):
    """Find a product by name - exact match first, then fuzzy (contains) match."""
    # Exact match
    cursor = await db.execute(
        "SELECT id, name, sell_price FROM products WHERE phone = ? AND LOWER(name) = LOWER(?)",
        (phone, name),
    )
    row = await cursor.fetchone()
    if row:
        return row

    # Contains match: "rice" matches "rice bag", "bag of rice", etc.
    cursor = await db.execute(
        "SELECT id, name, sell_price FROM products WHERE phone = ? AND LOWER(name) LIKE ?",
        (phone, f"%{name.lower()}%"),
    )
    row = await cursor.fetchone()
    if row:
        return row

    # Reverse contains: "bag of rice" matches stored "rice"
    cursor = await db.execute(
        "SELECT id, name, sell_price FROM products WHERE phone = ?",
        (phone,),
    )
    rows = await cursor.fetchall()
    for r in rows:
        if r[1].lower() in name.lower():
            return r

    return None


async def _get_or_create_product(db, phone, name, unit="piece", sell_price=0, cost_price=0):
    found = await _find_product(db, phone, name)
    if found:
        return found[0]

    cursor = await db.execute(
        """INSERT INTO products (phone, name, unit, sell_price, cost_price)
           VALUES (?, ?, ?, ?, ?)""",
        (phone, name, unit, sell_price, cost_price),
    )
    await db.commit()
    return cursor.lastrowid


async def _find_similar_customer(db, phone, name):
    """Find existing customer name by fuzzy match.
    Returns (matched_name, match_type) where match_type is:
    - 'exact': case-insensitive exact match (safe to auto-use)
    - 'fuzzy': similar name found (needs confirmation)
    - None: no match found (new customer)
    """
    cursor = await db.execute(
        "SELECT DISTINCT customer FROM credits WHERE phone = ?", (phone,)
    )
    rows = await cursor.fetchall()
    name_lower = name.lower().replace(" ", "")

    for row in rows:
        existing = row[0]
        existing_lower = existing.lower().replace(" ", "")
        # Exact match (case-insensitive) — safe to auto-use
        if name_lower == existing_lower:
            return existing, "exact"

    # Second pass for fuzzy matches — needs confirmation
    for row in rows:
        existing = row[0]
        existing_lower = existing.lower().replace(" ", "")
        # One contains the other
        if name_lower in existing_lower or existing_lower in name_lower:
            return existing, "fuzzy"
        # High character overlap
        if len(name_lower) >= 4 and len(existing_lower) >= 4:
            shorter = min(name_lower, existing_lower, key=len)
            longer = max(name_lower, existing_lower, key=len)
            matches = sum(1 for c in shorter if c in longer)
            if matches / len(shorter) >= 0.8:
                return existing, "fuzzy"

    return name, None


async def _save_pending(db, phone, action_data):
    """Save a pending action for confirmation."""
    await db.execute(
        "INSERT OR REPLACE INTO pending_actions (phone, action_data) VALUES (?, ?)",
        (phone, json.dumps(action_data)),
    )
    await db.commit()


async def _get_pending(db, phone):
    """Get and clear pending action."""
    cursor = await db.execute(
        "SELECT action_data FROM pending_actions WHERE phone = ?", (phone,)
    )
    row = await cursor.fetchone()
    if row:
        await db.execute("DELETE FROM pending_actions WHERE phone = ?", (phone,))
        await db.commit()
        return json.loads(row[0])
    return None


async def _add_credit(db, phone, customer, amount, note=""):
    await db.execute(
        """INSERT INTO credits (phone, customer, amount, note)
           VALUES (?, ?, ?, ?)""",
        (phone, customer, amount, note),
    )
