"""Business logic handlers for each intent."""
from app.database import get_db
from app.responses import get_response


def _fmt(num: float) -> str:
    """Format number with commas: 15000 -> 15,000"""
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"


async def handle_record_sale(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity", 1))
    unit = data.get("unit", "piece")
    total = float(data.get("total", 0))
    unit_price = float(data.get("unit_price", 0))
    customer = data.get("customer")
    is_credit = data.get("is_credit", False)

    if total and not unit_price:
        unit_price = total / quantity
    elif unit_price and not total:
        total = unit_price * quantity

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

    # Deduct stock
    await db.execute(
        "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
        (quantity, product_id),
    )

    # Record sale
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

    # Check low stock warning
    cursor = await db.execute(
        "SELECT stock_qty, unit FROM products WHERE id = ?", (product_id,)
    )
    row = await cursor.fetchone()
    low_stock_msg = ""
    if row and row[0] <= 3 and row[0] > 0:
        low_stock_msg = "\n" + get_response("stock_low", lang, product=product, quantity=_fmt(row[0]), unit=row[1])

    result = get_response(
        "sale_recorded", lang,
        quantity=_fmt(quantity), unit=unit, product=product, total=_fmt(total),
        credit_note=credit_note,
    ) + low_stock_msg

    # Drip hint for new users
    sale_count = (await (await db.execute(
        "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if sale_count <= 3:
        result += get_response("hint_after_sale", lang)

    return result


async def handle_add_stock(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity", 1))
    unit = data.get("unit", "piece")
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

    # Drip hint for new users
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

    remaining_payment = amount
    for row in rows:
        credit_id, credit_amount, already_paid = row[0], row[1], row[2]
        outstanding = credit_amount - already_paid
        if remaining_payment >= outstanding:
            await db.execute(
                "UPDATE credits SET paid = amount, settled = 1, updated_at = datetime('now') WHERE id = ?",
                (credit_id,),
            )
            remaining_payment -= outstanding
        else:
            await db.execute(
                "UPDATE credits SET paid = paid + ?, updated_at = datetime('now') WHERE id = ?",
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
            """SELECT customer, SUM(amount - paid) as owed FROM credits
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
    return get_response(
        "credits_list", lang,
        credit_list=credit_list, total=_fmt(total),
    )


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

    return get_response(
        "expense_recorded", lang,
        amount=_fmt(amount), description=description,
    )


async def handle_check_expenses(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    period = data.get("period", "today")

    if period == "today":
        date_filter = "date(created_at) = date('now')"
        period_text = "today" if lang == "english" else "today"
    elif period == "week":
        date_filter = "created_at >= datetime('now', '-7 days')"
        period_text = "this week" if lang == "english" else "this week"
    else:
        date_filter = "created_at >= datetime('now', '-30 days')"
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


async def handle_daily_summary(phone: str, data: dict, lang: str) -> str:
    db = await get_db()

    # Sales today
    cursor = await db.execute(
        """SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales
           WHERE phone = ? AND date(created_at) = date('now')""",
        (phone,),
    )
    row = await cursor.fetchone()
    sales_count, sales_total = row[0], row[1]

    # Expenses today
    cursor = await db.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM expenses
           WHERE phone = ? AND date(created_at) = date('now')""",
        (phone,),
    )
    expense_total = (await cursor.fetchone())[0]

    # Credits given today
    cursor = await db.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM credits
           WHERE phone = ? AND date(created_at) = date('now')""",
        (phone,),
    )
    credit_total = (await cursor.fetchone())[0]

    # Payments received today
    cursor = await db.execute(
        """SELECT COALESCE(SUM(paid), 0) FROM credits
           WHERE phone = ? AND date(updated_at) = date('now') AND paid > 0""",
        (phone,),
    )
    payment_total = (await cursor.fetchone())[0]

    if sales_count == 0 and expense_total == 0 and credit_total == 0:
        return get_response("no_activity", lang)

    net_cash = sales_total - credit_total + payment_total - expense_total

    # Top products
    cursor = await db.execute(
        """SELECT product_name, SUM(quantity), SUM(total) FROM sales
           WHERE phone = ? AND date(created_at) = date('now')
           GROUP BY product_name ORDER BY SUM(total) DESC LIMIT 3""",
        (phone,),
    )
    top = await cursor.fetchall()
    if top:
        header = "Top items:" if lang == "english" else "Wetin sell pass:"
        top_products = header + "\n" + "\n".join(
            f"  {r[0]}: {_fmt(r[1])} sold = {_fmt(r[2])} naira" for r in top
        )
    else:
        top_products = ""

    return get_response(
        "daily_summary", lang,
        sales_count=sales_count,
        sales_total=_fmt(sales_total),
        expense_total=_fmt(expense_total),
        credit_total=_fmt(credit_total),
        payment_total=_fmt(payment_total),
        net_cash=_fmt(net_cash),
        top_products=top_products,
    )


async def handle_set_price(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    unit = data.get("unit", "piece")
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
    new_lang = data.get("language", "pidgin").lower()
    if new_lang not in ("pidgin", "english"):
        new_lang = "pidgin"

    await db.execute("UPDATE shops SET language = ? WHERE phone = ?", (new_lang, phone))
    await db.commit()

    return get_response("language_changed", new_lang)


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


async def _add_credit(db, phone, customer, amount, note=""):
    await db.execute(
        """INSERT INTO credits (phone, customer, amount, note)
           VALUES (?, ?, ?, ?)""",
        (phone, customer, amount, note),
    )
