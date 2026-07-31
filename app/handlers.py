"""Business logic handlers for each intent."""
import json
import re
from datetime import datetime, timedelta
from app.database import get_db
from app.responses import get_response


def _fmt(num: float) -> str:
    """Format number with commas: 15000 -> 15,000"""
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"


_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _resolve_when(when: str) -> str | None:
    """Convert 'yesterday', '-2', or day names to a WAT datetime string. None = now."""
    if not when or when == "today":
        return None
    # UTC+1 for Nigeria (WAT)
    now_wat = datetime.utcnow() + timedelta(hours=1)
    if when == "yesterday":
        dt = now_wat - timedelta(days=1)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    # Day name: "saturday", "last friday"
    day_key = when.lower().replace("last ", "").strip()
    if day_key in _DAY_NAMES:
        target_dow = _DAY_NAMES[day_key]
        current_dow = now_wat.weekday()
        days_back = (current_dow - target_dow) % 7
        if days_back == 0:
            days_back = 7  # "saturday" on a saturday means last saturday
        dt = now_wat - timedelta(days=days_back)
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

    # Save original NLU values before recalculation (needed for ambiguity check)
    raw_unit_price = unit_price
    raw_total = total

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

    # Price ambiguity: "3 bags for 25 thousand" — each or total?
    if data.get("price_ambiguous") and quantity > 1:
        # Figure out the user's stated number from raw NLU values
        # NLU might set unit_price=X and total=X (same), or total=X*qty
        # Use raw_unit_price as the user's number (what they actually said)
        user_price = raw_unit_price or raw_total
        as_total = user_price                    # interpretation: user_price is the total
        as_each_unit = user_price / quantity     # ... so each unit costs this
        as_each = user_price                     # interpretation: user_price is per-unit
        as_each_total = user_price * quantity    # ... so total is this
        # Save both interpretations for confirm handler
        data["_price_as_total"] = as_total       # if user meant total
        data["_price_as_each"] = as_each         # if user meant each (per unit)
        await _save_pending(db, phone, {
            "action": "price_clarification",
            "data": data,
            "lang": lang,
        })
        if lang == "pidgin":
            return (
                f"You talk {_fmt(quantity)} {unit} {product} for {_fmt(user_price)} naira.\n\n"
                f"Na {_fmt(user_price)} total, abi {_fmt(user_price)} each?\n\n"
                f"Say \"yes\" if na {_fmt(as_total)} total ({_fmt(as_each_unit)} each).\n"
                f"Say \"no\" if na {_fmt(user_price)} each ({_fmt(as_each_total)} total)."
            )
        return (
            f"You said {_fmt(quantity)} {unit} {product} for {_fmt(user_price)} naira.\n\n"
            f"Is that {_fmt(user_price)} total, or {_fmt(user_price)} each?\n\n"
            f"Say \"yes\" if {_fmt(as_total)} total ({_fmt(as_each_unit)} each).\n"
            f"Say \"no\" if {_fmt(user_price)} each ({_fmt(as_each_total)} total)."
        )

    # Credit ambiguity: customer mentioned but credit not explicit
    if customer and not is_credit and data.get("credit_ambiguous"):
        data["_skip_customer_match"] = True
        await _save_pending(db, phone, {
            "action": "credit_clarification",
            "data": data,
            "lang": lang,
        })
        if lang == "pidgin":
            return (
                f"{customer} buy {_fmt(quantity)} {unit} {product} = {_fmt(total)} naira.\n\n"
                f"Na cash abi credit?\n\n"
                f"Say \"yes\" if na cash. Say \"no\" if na credit."
            )
        return (
            f"{customer} bought {_fmt(quantity)} {unit} {product} = {_fmt(total)} naira.\n\n"
            f"Was that cash or credit?\n\n"
            f"Say \"yes\" if cash. Say \"no\" if credit."
        )

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

    # Show unit price when quantity > 1 so users can catch pricing mistakes
    price_detail = ""
    if quantity > 1:
        price_detail = f" at {_fmt(unit_price)} each"

    result = get_response(
        "sale_recorded", lang,
        quantity=_fmt(quantity), unit=unit, product=product, total=_fmt(total),
        credit_note=credit_note, price_detail=price_detail,
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
        # Rotate discovery hints as the user records more sales
        sale_count = (await (await db.execute(
            "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
        )).fetchone())[0]
        if sale_count == 1:
            result += get_response("hint_after_sale", lang)
        elif sale_count == 2:
            result += get_response("hint_undo", lang)
        elif sale_count == 3:
            result += get_response("hint_discover_expenses", lang)
        elif sale_count == 5:
            hint = await _get_discovery_hint(db, phone, lang)
            if hint:
                result += hint
        elif sale_count == 8:
            hint = await _get_discovery_hint(db, phone, lang)
            if hint:
                result += hint
        elif sale_count == 12:
            result += get_response("hint_discover_backdate", lang)
        elif sale_count == 15:
            result += get_response("hint_discover_check_sales", lang)

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

    # Duplicate detection: if the user just got a voice name check and is now
    # re-sending the same credit with a different name, treat as a rename.
    if not data.get("_skip_voice_dedup"):
        pending = await _peek_pending(db, phone)
        if pending and pending.get("action") == "voice_name_correction":
            old_name = pending["old_customer"]
            old_amount = pending["amount"]
            if amount == old_amount and customer.lower() != old_name.lower():
                # This looks like a correction — rename instead of adding a duplicate
                await _clear_pending(db, phone)
                await db.execute(
                    "UPDATE credits SET customer = ? WHERE phone = ? AND LOWER(customer) = LOWER(?)",
                    (customer, phone, old_name),
                )
                await db.execute(
                    "UPDATE payments SET customer = ? WHERE phone = ? AND LOWER(customer) = LOWER(?)",
                    (customer, phone, old_name),
                )
                await db.commit()
                if lang == "pidgin":
                    return f"I don change \"{old_name}\" to \"{customer}\". No double record."
                return f"Fixed! Changed \"{old_name}\" to \"{customer}\". No duplicate."

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

    # Voice name verification: if this is a NEW customer from a voice note,
    # give the user a chance to correct the name before it gets entrenched.
    # Save pending so we can detect duplicates if they re-send the command.
    if match_type is None and data.get("_is_voice"):
        result += get_response("hint_voice_name_check", lang, customer=customer)
        await _save_pending(db, phone, {
            "action": "voice_name_correction",
            "old_customer": customer,
            "amount": amount,
        })

    # Drip hints — credit-related discovery
    credit_count = (await (await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if credit_count <= 2:
        result += get_response("hint_after_credit", lang, customer=customer)
    elif credit_count == 4:
        result += get_response("hint_credit_reminder", lang, customer=customer)
    elif credit_count == 6:
        result += get_response("hint_discover_receipt", lang, customer=customer)

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
        not_found = get_response("customer_not_found", lang, customer=customer)
        if data.get("_is_voice"):
            not_found += get_response("hint_voice_name_spell", lang)
        return not_found

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


async def handle_payment_and_credit(phone: str, data: dict, lang: str) -> str:
    """Handle a combined payment + new credit for the same customer."""
    customer = data.get("customer", "Customer")
    payment_amount = float(data.get("payment_amount", 0))
    credit_amount = float(data.get("credit_amount", 0))
    credit_note = data.get("credit_note", "")

    # Process the payment first
    payment_data = {"customer": customer, "amount": payment_amount, "_skip_customer_match": True}
    # Find similar customer once for both operations
    db = await get_db()
    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type == "fuzzy":
        data["_confirmed_customer"] = matched
        data["_original_customer"] = customer
        await _save_pending(db, phone, {"action": "payment_and_credit", "data": data, "lang": lang})
        return get_response("confirm_customer", lang, original=customer, matched=matched)
    if match_type == "exact":
        customer = matched

    payment_data = {"customer": customer, "amount": payment_amount, "_skip_customer_match": True}
    payment_result = await handle_record_payment(phone, payment_data, lang)

    # Process the new credit
    credit_data = {
        "customer": customer, "amount": credit_amount, "note": credit_note,
        "_skip_customer_match": True, "_skip_voice_dedup": True,
    }
    credit_result = await handle_record_credit(phone, credit_data, lang)

    # Combine the two results
    return payment_result + "\n\n" + credit_result


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


async def handle_check_payments(phone: str, data: dict, lang: str) -> str:
    """Show payment summary for a period."""
    db = await get_db()
    period = data.get("period", "today")

    if period == "today":
        date_filter = "date(created_at) = date('now', '+1 hours')"
        period_label = "today"
    elif period == "yesterday":
        date_filter = "date(created_at) = date('now', '+1 hours', '-1 day')"
        period_label = "yesterday"
    elif period == "week":
        date_filter = "created_at >= datetime('now', '+1 hours', '-7 days')"
        period_label = "this week"
    else:
        date_filter = "created_at >= datetime('now', '+1 hours', '-30 days')"
        period_label = "this month"

    cursor = await db.execute(
        f"""SELECT MIN(customer), SUM(amount) FROM payments
            WHERE phone = ? AND {date_filter}
            GROUP BY LOWER(customer)
            ORDER BY SUM(amount) DESC""",
        (phone,),
    )
    rows = await cursor.fetchall()

    if not rows:
        if lang == "pidgin":
            return f"Nobody pay you {period_label}."
        return f"No payments received {period_label}."

    total = sum(r[1] for r in rows)
    payment_list = "\n".join(f"  {r[0]}: {_fmt(r[1])} naira" for r in rows)

    if lang == "pidgin":
        return f"People wey pay you {period_label}:\n{payment_list}\n\nTotal: {_fmt(total)} naira"
    return f"Payments received {period_label}:\n{payment_list}\n\nTotal: {_fmt(total)} naira"


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


async def handle_multi_expense(phone: str, data: dict, lang: str) -> str:
    """Record multiple expenses from a single message."""
    db = await get_db()
    items = data.get("items", [])
    if not items:
        return get_response("error", lang)

    results = []
    total = 0
    for item in items:
        description = item.get("description", "expense")
        amount = float(item.get("amount", 0))
        category = item.get("category", "other")
        if amount <= 0:
            continue
        await db.execute(
            "INSERT INTO expenses (phone, description, amount, category) VALUES (?, ?, ?, ?)",
            (phone, description, amount, category),
        )
        results.append(f"  {description}: {_fmt(amount)} naira")
        total += amount

    await db.commit()

    if not results:
        return get_response("error", lang)

    expense_list = "\n".join(results)
    if lang == "pidgin":
        return f"Saved! You spend:\n{expense_list}\n\nTotal: {_fmt(total)} naira"
    return f"Saved! You spent:\n{expense_list}\n\nTotal: {_fmt(total)} naira"


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
        f"SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND {date_filter}",
        (phone,),
    )
    row = await cursor.fetchone()
    sales_count, sales_total = int(row[0]), row[1]

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

    # Profit estimate: revenue minus cost-of-goods-sold (only if cost data exists)
    # Qualify created_at with table alias to avoid ambiguity in the JOIN
    profit_date_filter = date_filter.replace("created_at", "s.created_at")
    cursor = await db.execute(
        f"""SELECT COALESCE(SUM(s.quantity * p.cost_price), 0)
            FROM sales s JOIN products p ON s.product_id = p.id
            WHERE s.phone = ? AND {profit_date_filter} AND p.cost_price > 0""",
        (phone,),
    )
    cost_of_goods = (await cursor.fetchone())[0]
    if cost_of_goods > 0 and sales_total > 0:
        profit = sales_total - cost_of_goods - expense_total
        if lang == "pidgin":
            result += f"\nYour gain (after cost and expenses): {_fmt(profit)} naira."
        else:
            result += f"\nProfit (after cost and expenses): {_fmt(profit)} naira."

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

    result = get_response(
        "price_set", lang,
        product=product, price=_fmt(sell_price), unit=unit,
    )

    # Auto-complete pending multi-sale items that needed this price
    pending = await _peek_pending(db, phone)
    if pending and pending.get("action") == "multi_sale_pending":
        pending_items = pending.get("items", [])
        pending_lang = pending.get("lang", lang)
        when = pending.get("when", "today")
        completed = []
        still_needs_price = []

        for item in pending_items:
            item_product = _normalize_product_name(item.get("product", ""))
            # Check if this item now has a price (either the one just set, or stored)
            existing = await _find_product(db, phone, item_product)
            if existing and existing[2] > 0:
                item["unit_price"] = existing[2]
                item["total"] = existing[2] * float(item.get("quantity", 1))
                item["action"] = "record_sale"
                if "when" not in item:
                    item["when"] = when
                sale_result = await handle_record_sale(phone, item, pending_lang)
                lines = sale_result.split("\n")
                sale_line = lines[0]
                if len(lines) > 1 and ("credit" in lines[1].lower() or "owe" in lines[1].lower()):
                    sale_line += "\n" + lines[1]
                completed.append(sale_line)
            else:
                still_needs_price.append(item)

        if completed:
            result += "\n\n" + "\n".join(completed)

        if still_needs_price:
            # Update pending with remaining items
            await _save_pending(db, phone, {
                "action": "multi_sale_pending",
                "items": still_needs_price,
                "when": when,
                "lang": pending_lang,
            })
            names = ", ".join(i.get("product", "item") for i in still_needs_price)
            if pending_lang == "pidgin":
                result += f"\n\nI still need price for: {names}."
            else:
                result += f"\n\nI still need a price for: {names}."
        else:
            # All done — clear pending
            await _clear_pending(db, phone)

    return result


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

    # Long voice confirmation: user says the transcription is correct — process it
    if pending.get("action") == "long_voice_confirm":
        return "__replay__:" + pending["text"]

    if "data" not in pending:
        if lang == "pidgin":
            return "Nothing to confirm. Just tell me wetin you wan do."
        return "Nothing to confirm. Just tell me what you need."

    pending_data = pending["data"]
    pending_lang = pending.get("lang", lang)

    # Non-customer actions (no name to resolve)
    if pending["action"] == "delete_data_confirmed":
        return await handle_delete_data_confirmed(phone, pending_data, pending_lang)

    # Price clarification: "yes" = total interpretation
    if pending["action"] == "price_clarification":
        pending_data.pop("price_ambiguous", None)
        # "yes" = the amount is the total
        qty = float(pending_data.get("quantity", 1))
        as_total = float(pending_data.pop("_price_as_total", 0))
        pending_data.pop("_price_as_each", None)
        if as_total and qty:
            pending_data["total"] = as_total
            pending_data["unit_price"] = as_total / qty
        return await handle_record_sale(phone, pending_data, pending_lang)

    # Credit clarification: "yes" = cash (not credit)
    if pending["action"] == "credit_clarification":
        pending_data.pop("credit_ambiguous", None)
        pending_data["is_credit"] = False
        return await handle_record_sale(phone, pending_data, pending_lang)

    # Use the confirmed (matched) customer name
    pending_data["customer"] = pending_data.pop("_confirmed_customer")
    pending_data.pop("_original_customer", None)
    pending_data["_skip_customer_match"] = True

    if pending["action"] == "record_credit":
        return await handle_record_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "record_payment":
        return await handle_record_payment(phone, pending_data, pending_lang)
    elif pending["action"] == "customer_statement":
        return await handle_customer_statement(phone, pending_data, pending_lang)
    elif pending["action"] == "payment_and_credit":
        return await handle_payment_and_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "mark_credit":
        return await handle_mark_credit(phone, pending_data, pending_lang)

    return get_response("error", lang)


async def handle_confirm_no(phone: str, data: dict, lang: str) -> str:
    """User rejected the fuzzy match — use original name as new customer."""
    db = await get_db()
    pending = await _get_pending(db, phone)
    if not pending:
        if lang == "pidgin":
            return "Nothing to confirm. Just tell me wetin you wan do."
        return "Nothing to confirm. Just tell me what you need."

    # Long voice confirmation: user says transcription was wrong — ask to resend
    if pending.get("action") == "long_voice_confirm":
        if lang == "pidgin":
            return "No wahala. Send another shorter voice note and I go try again."
        return "No problem. Send a shorter voice note and I'll try again."

    if "data" not in pending:
        if lang == "pidgin":
            return "Nothing to confirm. Just tell me wetin you wan do."
        return "Nothing to confirm. Just tell me what you need."

    pending_data = pending["data"]
    pending_lang = pending.get("lang", lang)

    # Non-customer actions
    if pending["action"] == "delete_data_confirmed":
        return get_response("delete_cancelled", pending_lang)

    # Price clarification: "no" = each interpretation — recalculate
    if pending["action"] == "price_clarification":
        pending_data.pop("price_ambiguous", None)
        # "no" = the amount is per-unit price
        qty = float(pending_data.get("quantity", 1))
        as_each = float(pending_data.pop("_price_as_each", 0)) or float(pending_data.get("unit_price", 0))
        pending_data.pop("_price_as_total", None)
        pending_data["unit_price"] = as_each
        pending_data["total"] = as_each * qty
        return await handle_record_sale(phone, pending_data, pending_lang)

    # Credit clarification: "no" = credit (not cash)
    if pending["action"] == "credit_clarification":
        pending_data.pop("credit_ambiguous", None)
        pending_data["is_credit"] = True
        customer = pending_data.get("customer", "Customer")
        return await handle_record_sale(phone, pending_data, pending_lang)

    # Use the original (new) customer name
    pending_data["customer"] = pending_data.pop("_original_customer")
    pending_data.pop("_confirmed_customer", None)
    pending_data["_skip_customer_match"] = True

    if pending["action"] == "record_credit":
        return await handle_record_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "record_payment":
        return await handle_record_payment(phone, pending_data, pending_lang)
    elif pending["action"] == "customer_statement":
        return await handle_customer_statement(phone, pending_data, pending_lang)
    elif pending["action"] == "payment_and_credit":
        return await handle_payment_and_credit(phone, pending_data, pending_lang)
    elif pending["action"] == "mark_credit":
        return await handle_mark_credit(phone, pending_data, pending_lang)

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

    # Get the last sale, optionally filtering by product and/or time
    product = data.get("product")
    when_filter = data.get("when")
    where = "phone = ?"
    params = [phone]
    if product:
        product = _normalize_product_name(product)
        where += " AND LOWER(product_name) = LOWER(?)"
        params.append(product)
    if when_filter and when_filter != "today":
        resolved = _resolve_when(when_filter)
        if resolved:
            where += " AND date(created_at) = ?"
            params.append(resolved[:10])
    cursor = await db.execute(
        f"SELECT id, product_name, quantity, unit_price, total, product_id FROM sales WHERE {where} ORDER BY created_at DESC LIMIT 1",
        tuple(params),
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


async def handle_mark_credit(phone: str, data: dict, lang: str) -> str:
    """Retroactively mark the last sale as credit — 'that was on credit'."""
    db = await get_db()
    customer = data.get("customer")

    # Find the most recent non-credit sale
    cursor = await db.execute(
        "SELECT id, product_name, quantity, unit_price, total, customer FROM sales "
        "WHERE phone = ? AND is_credit = 0 ORDER BY created_at DESC LIMIT 1",
        (phone,),
    )
    row = await cursor.fetchone()
    if not row:
        if lang == "pidgin":
            return "I no see any recent sale to mark as credit."
        return "No recent sale to mark as credit."

    sale_id, product_name, quantity, unit_price, total, existing_customer = (
        row[0], row[1], row[2], row[3], row[4], row[5]
    )

    # Use existing customer from the sale if no new one given
    if not customer:
        customer = existing_customer
    if not customer:
        if lang == "pidgin":
            return "Who buy am on credit? Tell me the customer name."
        return "Who bought on credit? Tell me the customer name."

    # Customer name matching
    if not data.get("_skip_customer_match"):
        matched, match_type = await _find_similar_customer(db, phone, customer)
        if match_type == "fuzzy":
            data["_confirmed_customer"] = matched
            data["_original_customer"] = customer
            await _save_pending(db, phone, {"action": "mark_credit", "data": data, "lang": lang})
            return get_response("confirm_customer", lang, original=customer, matched=matched)
        if match_type == "exact":
            customer = matched

    # Update the sale to credit
    await db.execute(
        "UPDATE sales SET is_credit = 1, customer = ? WHERE id = ?",
        (customer, sale_id),
    )

    # Add credit record
    note = f"{_fmt(quantity)} {product_name}"
    await _add_credit(db, phone, customer, total, note)
    await db.commit()

    if lang == "pidgin":
        return f"Done! {product_name} ({_fmt(total)} naira) don mark as credit for {customer}."
    return f"Done! {product_name} ({_fmt(total)} naira) marked as credit for {customer}."


async def handle_undo(phone: str, data: dict, lang: str) -> str:
    """Undo the last recorded action (sale, expense, credit, or stock entry)."""
    db = await get_db()

    # Optional product filter: "undo the rice sale"
    product_filter = data.get("product")
    if product_filter:
        product_filter = _normalize_product_name(product_filter)

    # Optional time filter: "undo the sale from yesterday"
    when_filter = data.get("when")
    when_date = None
    if when_filter and when_filter != "today":
        resolved = _resolve_when(when_filter)
        if resolved:
            when_date = resolved[:10]  # just the date part YYYY-MM-DD
    elif when_filter == "today" or not when_filter:
        # No date filter — search all time
        when_date = None

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
        # If product filter given, only search product-related tables
        if product_filter and table in ("expenses", "credits", "payments"):
            continue
        where = "phone = ?"
        params = [phone]
        if product_filter and desc_col == "product_name":
            where += " AND LOWER(product_name) = LOWER(?)"
            params.append(product_filter)
        if when_date:
            where += " AND date(created_at) = ?"
            params.append(when_date)
        cursor = await db.execute(
            f"SELECT id, {desc_col}, {amount_col}, created_at"
            + (f", {qty_col}, {pid_col}" if qty_col else "")
            + f" FROM {table} WHERE {where} ORDER BY created_at DESC LIMIT 1",
            tuple(params),
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
    db = await get_db()
    items = data.get("items", [])
    if not items:
        return get_response("not_understood", lang)

    results = []
    grand_total = 0
    needs_price = []

    for item in items:
        # Process each item as a sale, preserving per-item credit/customer
        item["action"] = "record_sale"
        if "when" not in item and "when" in data:
            item["when"] = data["when"]
        # Inherit top-level customer/credit if item doesn't specify its own
        if "customer" not in item and "customer" in data and data["customer"]:
            item["customer"] = data["customer"]
        if "is_credit" not in item and data.get("is_credit"):
            item["is_credit"] = True
        result = await handle_record_sale(phone, item, lang)
        # Keep the sale line + credit note (first 2 lines), drop stock/hint noise
        lines = result.split("\n")
        sale_line = lines[0]

        # Check if the handler asked for a price (no stored price found)
        if "How much" in result or "How much" in sale_line:
            needs_price.append(item.get("product", "item"))
            continue

        # Include credit note if present (second line)
        if len(lines) > 1 and ("credit" in lines[1].lower() or "owe" in lines[1].lower()):
            sale_line += "\n" + lines[1]
        results.append(sale_line)
        # Recalculate — don't trust LLM total
        qty = float(item.get("quantity", 1))
        price = float(item.get("unit_price", 0))
        grand_total += qty * price

    summary = "\n".join(results)
    if grand_total > 0:
        if lang == "pidgin":
            summary += f"\n\nTotal: {_fmt(grand_total)} naira for everything."
        else:
            summary += f"\n\nTotal: {_fmt(grand_total)} naira for all items."

    if needs_price:
        # Save unpriced items as pending so set_price can auto-complete them
        unpriced = [item for item in items if item.get("product", "").lower() in [n.lower() for n in needs_price]]
        if unpriced:
            await _save_pending(db, phone, {
                "action": "multi_sale_pending",
                "items": unpriced,
                "when": data.get("when", "today"),
                "lang": lang,
            })
        names = ", ".join(needs_price)
        if lang == "pidgin":
            summary += f"\n\nI no know the price for: {names}. Tell me the price and I go record am."
        else:
            summary += f"\n\nI don't have a price for: {names}. Tell me the price and I'll record them."

    return summary


async def handle_customer_statement(phone: str, data: dict, lang: str) -> str:
    """Generate a shareable receipt/statement link for a specific customer."""
    from app.config import BASE_URL
    from app.report import get_or_create_customer_receipt_token

    customer = data.get("customer", "")
    if not customer:
        if lang == "pidgin":
            return "Who receipt you want? Tell me like: \"receipt for Mama Joy\""
        return "Which customer? Tell me like: \"receipt for Mama Joy\""

    db = await get_db()

    # Normalize customer name
    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type == "fuzzy":
        data["_confirmed_customer"] = matched
        data["_original_customer"] = customer
        await _save_pending(db, phone, {"action": "customer_statement", "data": data, "lang": lang})
        return get_response("confirm_customer", lang, original=customer, matched=matched)
    if match_type == "exact":
        customer = matched

    # Check this customer actually exists in credits
    cursor = await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ? AND LOWER(customer) = LOWER(?)",
        (phone, customer),
    )
    if (await cursor.fetchone())[0] == 0:
        return get_response("customer_not_found", lang, customer=customer)

    token = await get_or_create_customer_receipt_token(phone, customer)
    url = f"{BASE_URL.rstrip('/')}/receipt/{token}"
    return get_response("customer_receipt_link", lang, customer=customer, url=url)


async def handle_merge_products(phone: str, data: dict, lang: str) -> str:
    """Merge two product names — combine sales, stock, etc. under one name."""
    db = await get_db()
    old_name = _normalize_product_name(data.get("old_name", ""))
    new_name = _normalize_product_name(data.get("new_name", ""))

    if not old_name or not new_name:
        if lang == "pidgin":
            return "Tell me like: \"coke and coca cola na the same thing\""
        return "Tell me like: \"coke and coca cola are the same thing\""

    # Find both products
    old_product = await _find_product(db, phone, old_name)
    new_product = await _find_product(db, phone, new_name)

    if not old_product:
        if lang == "pidgin":
            return f"I no see \"{old_name}\" for your products."
        return f"I can't find \"{old_name}\" in your products."

    if not new_product:
        # Just rename the old product
        await db.execute("UPDATE products SET name = ? WHERE id = ?", (new_name, old_product[0]))
        await db.execute("UPDATE sales SET product_name = ? WHERE phone = ? AND product_id = ?",
                         (new_name, phone, old_product[0]))
        await db.execute("UPDATE stock_entries SET product_name = ? WHERE phone = ? AND product_id = ?",
                         (new_name, phone, old_product[0]))
        await db.commit()
        if lang == "pidgin":
            return f"I don change \"{old_name}\" to \"{new_name}\"."
        return f"Renamed \"{old_name}\" to \"{new_name}\"."

    # Both exist — merge old into new
    old_id, new_id = old_product[0], new_product[0]

    # Move sales and stock entries to the new product
    await db.execute("UPDATE sales SET product_id = ?, product_name = ? WHERE phone = ? AND product_id = ?",
                     (new_id, new_name, phone, old_id))
    await db.execute("UPDATE stock_entries SET product_id = ?, product_name = ? WHERE phone = ? AND product_id = ?",
                     (new_id, new_name, phone, old_id))

    # Combine stock quantities
    old_qty = (await (await db.execute("SELECT stock_qty FROM products WHERE id = ?", (old_id,))).fetchone())[0]
    await db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (old_qty, new_id))

    # Delete the old product
    await db.execute("DELETE FROM products WHERE id = ?", (old_id,))
    await db.commit()

    if lang == "pidgin":
        return f"I don join \"{old_name}\" with \"{new_name}\". All record now dey under \"{new_name}\"."
    return f"Merged \"{old_name}\" into \"{new_name}\". All records are now under \"{new_name}\"."


# ---- Helpers ----

# Common product aliases — maps variant names to canonical form.
# Only used as a fallback after exact/fuzzy match fails.
_PRODUCT_ALIASES = {
    "coca cola": "coke", "coca-cola": "coke",
    "minerals": "soft drink", "soda": "soft drink", "fizzy drink": "soft drink",
    "peanut": "groundnut",
    "gari": "garri",
    "noodles": "indomie", "instant noodles": "indomie",
    "sachet water": "water", "pure water": "water", "table water": "water",
    "tin milk": "peak milk", "evaporated milk": "peak milk",
    "agege bread": "bread", "sliced bread": "bread",
}


def _normalize_product_name(name: str) -> str:
    """Strip common qualifiers and apply alias normalization.

    E.g. "bag of rice" → "rice", "crate of minerals" → "soft drink",
         "bags of cement" → "cement", "coca cola" → "coke".
    """
    s = name.lower().strip()
    # Strip leading unit qualifiers: "bag of rice" → "rice"
    s = re.sub(
        r'^(bags?|crates?|cartons?|bottles?|pieces?|packs?|rolls?|kegs?|sachets?|dozens?|pairs?|bundles?|tins?|cups?)\s+of\s+',
        '', s,
    )
    s = s.strip()
    # Apply alias mapping
    return _PRODUCT_ALIASES.get(s, s)


async def _find_product(db, phone, name):
    """Find a product by name - exact match first, then word-boundary fuzzy match.

    Fuzzy matching only activates when the search term is 4+ characters and
    matches as a whole word inside the stored name (or vice-versa).  This
    prevents "rice" from matching "fried rice" while still allowing "cement"
    to match "cement bag".
    """
    name = _normalize_product_name(name)

    # Exact match (case-insensitive)
    cursor = await db.execute(
        "SELECT id, name, sell_price FROM products WHERE phone = ? AND LOWER(name) = LOWER(?)",
        (phone, name),
    )
    row = await cursor.fetchone()
    if row:
        return row

    # Only attempt fuzzy matching for names with 4+ characters to avoid
    # short-name collisions ("oil" matching "foil", "rice" matching "fried rice").
    if len(name) < 4:
        return None

    # Word-boundary match: the search term must appear as a complete word
    # in the stored name, or the stored name must appear as a complete word
    # in the search term.
    pattern = re.compile(r'\b' + re.escape(name.lower()) + r'\b')

    cursor = await db.execute(
        "SELECT id, name, sell_price FROM products WHERE phone = ?",
        (phone,),
    )
    rows = await cursor.fetchall()

    for r in rows:
        stored = r[1].lower()
        # Search term is a whole word inside stored name
        if pattern.search(stored):
            return r
        # Stored name is a whole word inside search term (guard against short names like "oil" matching "groundnut oil")
        if len(stored) >= 4:
            stored_pattern = re.compile(r'\b' + re.escape(stored) + r'\b')
            if stored_pattern.search(name.lower()):
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
            if len(name_lower) <= len(existing_lower):
                shorter, longer = name_lower, existing_lower
            else:
                shorter, longer = existing_lower, name_lower
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


async def _peek_pending(db, phone):
    """Read pending action without clearing it."""
    cursor = await db.execute(
        "SELECT action_data FROM pending_actions WHERE phone = ?", (phone,)
    )
    row = await cursor.fetchone()
    return json.loads(row[0]) if row else None


async def _clear_pending(db, phone):
    """Clear pending action."""
    await db.execute("DELETE FROM pending_actions WHERE phone = ?", (phone,))
    await db.commit()


async def _get_pending(db, phone):
    """Get and clear pending action."""
    pending = await _peek_pending(db, phone)
    if pending:
        await _clear_pending(db, phone)
    return pending


async def _add_credit(db, phone, customer, amount, note=""):
    await db.execute(
        """INSERT INTO credits (phone, customer, amount, note)
           VALUES (?, ?, ?, ?)""",
        (phone, customer, amount, note),
    )


async def handle_privacy(phone: str, data: dict, lang: str) -> str:
    """Show a plain-language privacy summary."""
    from app.config import BASE_URL
    url = f"{BASE_URL.rstrip('/')}/privacy"
    return get_response("privacy_summary", lang, url=url)


async def handle_delete_data(phone: str, data: dict, lang: str) -> str:
    """Initiate data deletion — asks for confirmation first."""
    db = await get_db()
    await _save_pending(db, phone, {"action": "delete_data_confirmed", "data": {}, "lang": lang})
    return get_response("delete_confirm", lang)


async def handle_delete_data_confirmed(phone: str, data: dict, lang: str) -> str:
    """Actually delete all user data after confirmation."""
    db = await get_db()
    # Delete from all tables in dependency order
    for table in ("sales", "stock_entries", "credits", "payments", "expenses",
                  "feedback", "pending_actions", "report_tokens", "customer_receipts", "products"):
        await db.execute(f"DELETE FROM {table} WHERE phone = ?", (phone,))
    await db.execute("DELETE FROM shops WHERE phone = ?", (phone,))
    await db.commit()
    return get_response("delete_done", lang)


async def handle_record_bulk_sale(phone: str, data: dict, lang: str) -> str:
    """Record a lump-sum daily total without specific products."""
    db = await get_db()
    total = float(data.get("total", 0))
    if total <= 0:
        if lang == "pidgin":
            return "How much you sell? Tell me the amount."
        return "How much did you sell? Tell me the amount."

    when = _resolve_when(data.get("when", "today"))
    product_name = "(general sales)"
    product_id = await _get_or_create_product(db, phone, product_name, "lump sum", 0)

    if when:
        await db.execute(
            """INSERT INTO sales (phone, product_id, product_name, quantity, unit_price, total, created_at)
               VALUES (?, ?, ?, 1, ?, ?, ?)""",
            (phone, product_id, product_name, total, total, when),
        )
    else:
        await db.execute(
            """INSERT INTO sales (phone, product_id, product_name, quantity, unit_price, total)
               VALUES (?, ?, ?, 1, ?, ?)""",
            (phone, product_id, product_name, total, total),
        )
    await db.commit()

    if lang == "pidgin":
        result = f"I don record {_fmt(total)} naira sales for today."
    else:
        result = f"Recorded {_fmt(total)} naira in sales."

    if data.get("when") == "yesterday":
        result = result.replace("for today", "for yesterday").replace("in sales", "in sales for yesterday")

    result += "\n" + get_response("hint_bulk_detail", lang)
    return result


async def handle_what_can_you_do(phone: str, data: dict, lang: str) -> str:
    """Show a personalized list of features the user hasn't tried yet."""
    db = await get_db()

    # Check which features they've used
    sale_count = (await (await db.execute(
        "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
    )).fetchone())[0]
    expense_count = (await (await db.execute(
        "SELECT COUNT(*) FROM expenses WHERE phone = ?", (phone,)
    )).fetchone())[0]
    stock_count = (await (await db.execute(
        "SELECT COUNT(*) FROM stock_entries WHERE phone = ?", (phone,)
    )).fetchone())[0]
    credit_count = (await (await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ?", (phone,)
    )).fetchone())[0]
    report_count = (await (await db.execute(
        "SELECT COUNT(*) FROM report_tokens WHERE phone = ?", (phone,)
    )).fetchone())[0]

    tips = []
    is_pidgin = lang == "pidgin"

    if sale_count == 0:
        tips.append('"I sell 3 bag rice, 5 thousand"' if is_pidgin else '"I sold 3 bags of rice for 5 thousand"')
    if credit_count == 0:
        tips.append('"Mama Joy owe me 5 thousand"' if is_pidgin else '"Mama Joy owes me 5 thousand"')
    if expense_count == 0:
        tips.append('"I spend 500 on transport"' if is_pidgin else '"I spent 500 on transport"')
    if stock_count == 0:
        tips.append('"I buy 10 bag cement"' if is_pidgin else '"I bought 10 bags of cement"')
    if sale_count > 0 or expense_count > 0:
        tips.append('"How my shop do today?"' if is_pidgin else '"How did my shop do today?"')
    if report_count == 0 and sale_count > 0:
        tips.append('"My report"' if is_pidgin else '"My report"')
    if credit_count > 0:
        tips.append('"Who owe me?"' if is_pidgin else '"Who owes me?"')
    # Always show these — users may not know
    tips.append('"Cancel am"' if is_pidgin else '"Cancel that" — fix mistakes')
    if sale_count >= 3:
        tips.append('"I sell rice yesterday"' if is_pidgin else '"I sold rice yesterday" — backdate')

    if not tips:
        return get_response("help", lang)

    header = "Here na some things I fit do for you:" if is_pidgin else "Here are some things I can do for you:"
    tip_list = "\n".join(f"- {t}" for t in tips[:6])  # Max 6 tips
    footer = "\nJust yarn to me normal!" if is_pidgin else "\nJust talk to me normally!"

    return f"{header}\n\n{tip_list}{footer}"


async def _get_discovery_hint(db, phone, lang):
    """Return a hint about the most relevant undiscovered feature."""
    # Check what features they've used (one query each, lightweight)
    expense_count = (await (await db.execute(
        "SELECT COUNT(*) FROM expenses WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if expense_count == 0:
        return get_response("hint_discover_expenses", lang)

    stock_count = (await (await db.execute(
        "SELECT COUNT(*) FROM stock_entries WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if stock_count == 0:
        return get_response("hint_discover_stock", lang)

    report_count = (await (await db.execute(
        "SELECT COUNT(*) FROM report_tokens WHERE phone = ?", (phone,)
    )).fetchone())[0]
    if report_count == 0:
        return get_response("hint_report", lang)

    # If they have credits, suggest receipt feature
    unsettled = (await (await db.execute(
        "SELECT COUNT(*) FROM credits WHERE phone = ? AND settled = 0", (phone,)
    )).fetchone())[0]
    if unsettled >= 2:
        # Get a customer name for the hint
        cursor = await db.execute(
            "SELECT customer FROM credits WHERE phone = ? AND settled = 0 LIMIT 1",
            (phone,),
        )
        row = await cursor.fetchone()
        if row:
            return get_response("hint_discover_receipt", lang, customer=row[0])

    return ""
