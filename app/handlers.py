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
        dt = (now_wat - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    # Day name: "saturday", "last friday"
    day_key = when.lower().replace("last ", "").strip()
    if day_key in _DAY_NAMES:
        target_dow = _DAY_NAMES[day_key]
        current_dow = now_wat.weekday()
        days_back = (current_dow - target_dow) % 7
        if days_back == 0:
            days_back = 7  # "saturday" on a saturday means last saturday
        dt = (now_wat - timedelta(days=days_back)).replace(hour=0, minute=0, second=0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        days = int(when)
        dt = (now_wat + timedelta(days=days)).replace(hour=0, minute=0, second=0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def handle_record_sale(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity") or 1)
    unit = data.get("unit") or "piece"
    total = float(data.get("total") or 0)
    unit_price = float(data.get("unit_price") or 0)
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

    # If no price given, try to use stored sell_price or last sale price
    if not total and not unit_price:
        existing = await _find_product(db, phone, product)
        if existing and existing[2] > 0:
            unit_price = existing[2]
            total = unit_price * quantity
        else:
            # No stored sell_price — check last sale price for this product
            last_price_row = None
            if existing:
                cursor = await db.execute(
                    "SELECT unit_price FROM sales WHERE phone = ? AND product_id = ? AND unit_price > 0 ORDER BY id DESC LIMIT 1",
                    (phone, existing[0]))
                last_price_row = await cursor.fetchone()
            if last_price_row and last_price_row[0] > 0:
                # Use last sale price but tell the user so they can correct
                unit_price = last_price_row[0]
                total = unit_price * quantity
                data["_used_last_price"] = True
                data["_last_unit_price"] = unit_price
            else:
                # No previous price at all — must ask
                await _save_pending(db, phone, {
                    "action": "price_needed",
                    "data": data,
                    "lang": lang,
                })
                return get_response("sale_needs_price", lang, product=product)

    # Price ambiguity: "3 bags for 25 thousand" — each or total?
    if data.get("price_ambiguous") and quantity > 1:
        # The user said ONE number without "each"/"per"/"total" keyword.
        # NLU puts the user's stated number in total; use raw_total as the ambiguous amount.
        user_price = raw_total or raw_unit_price
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

    backdate_note = ""
    when_val = data.get("when", "today")
    if when_val and when_val != "today":
        backdate_note = f" (recorded for {when_val})"

    result = get_response(
        "sale_recorded", lang,
        quantity=_fmt(quantity), unit=unit, product=product, total=_fmt(total),
        credit_note=credit_note, price_detail=price_detail,
    ) + backdate_note + low_stock_msg

    # If we used last sale price (no stored sell_price), tell the user
    if data.get("_used_last_price"):
        last_up = data["_last_unit_price"]
        if lang == "pidgin":
            result += f"\nI use the last price ({_fmt(last_up)} naira). If e don change, tell me \"set {product} price to [new price]\"."
        else:
            result += f"\nI used the last price ({_fmt(last_up)} naira). If it changed, say \"set {product} price to [new price]\"."

    # Repeat customer recognition (milestones: 5, 10, 20, 50 purchases)
    if customer:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM sales WHERE phone = ? AND LOWER(customer) = LOWER(?)",
            (phone, customer))
        cust_count = (await cursor.fetchone())[0]
        if cust_count in (5, 10, 20, 50):
            if lang == "pidgin":
                result += f"\n{customer} don buy from you {cust_count} times! Na your loyal customer o."
            else:
                result += f"\n{customer} has bought from you {cust_count} times! A loyal customer."

    # One contextual nudge — rotate discovery hints by total sale count
    # Rule: only ONE follow-on per response (hint, milestone, or insight — never stack)
    sale_count = (await (await db.execute(
        "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
    )).fetchone())[0]

    # Check for milestones first — they take priority over discovery hints
    milestone_msg = await _check_milestone(db, phone, sale_count, total, lang)
    if milestone_msg:
        result += milestone_msg
    elif sale_count == 1:
        result += get_response("hint_after_sale", lang)
    elif sale_count == 2:
        result += get_response("hint_undo", lang)
    elif sale_count == 3:
        result += get_response("hint_discover_expenses", lang)
    elif sale_count == 4 and not has_stock_data:
        result += get_response("hint_stock_unknown", lang, product=product)
    elif sale_count == 5:
        hint = await _get_discovery_hint(db, phone, lang)
        if hint:
            result += hint
    elif sale_count == 6:
        # Nudge text-only users to try voice notes
        voice_row = await (await db.execute(
            "SELECT voice_user FROM shops WHERE phone = ?", (phone,)
        )).fetchone()
        if voice_row and not voice_row[0]:
            result += get_response("hint_try_voice", lang)
    elif sale_count == 8:
        # Check if shop name is set; if not, hint about it
        shop_row = await (await db.execute(
            "SELECT name FROM shops WHERE phone = ?", (phone,)
        )).fetchone()
        if not (shop_row and shop_row[0]):
            result += get_response("hint_shop_name", lang)
        else:
            hint = await _get_discovery_hint(db, phone, lang)
            if hint:
                result += hint
    elif sale_count == 12:
        result += get_response("hint_discover_backdate", lang)
    elif sale_count == 15:
        result += get_response("hint_discover_check_sales", lang)
    elif sale_count == 20:
        result += get_response("hint_discover_weekly", lang)
    elif sale_count > 30 and sale_count % 10 == 0:
        # Sale-attached micro-insight: lightweight business insight every 10 sales
        # Rotates through: stock velocity, revenue pace, product comparison
        micro = await _get_sale_micro_insight(db, phone, product, product_id, lang)
        if micro:
            result += micro

    return result


async def handle_add_stock(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    quantity = float(data.get("quantity") or 1)
    unit = data.get("unit") or "piece"
    cost_price = float(data.get("cost_price") or 0)

    supplier = (data.get("supplier") or "").strip() or None

    product_id = await _get_or_create_product(db, phone, product, unit, 0, cost_price)

    # Update stock
    await db.execute(
        "UPDATE products SET stock_qty = stock_qty + ?, cost_price = CASE WHEN ? > 0 THEN ? ELSE cost_price END WHERE id = ?",
        (quantity, cost_price, cost_price, product_id),
    )

    # Record entry
    await db.execute(
        """INSERT INTO stock_entries (phone, product_id, product_name, quantity, cost_price, entry_type, supplier)
           VALUES (?, ?, ?, ?, ?, 'purchase', ?)""",
        (phone, product_id, product, quantity, cost_price, supplier),
    )
    await db.commit()

    price_note = ""
    if cost_price > 0:
        total_cost = cost_price * quantity
        price_note = f" Cost: {_fmt(total_cost)} naira ({_fmt(cost_price)} each)."

    supplier_note = ""
    if supplier:
        supplier_note = f" (from {supplier})"

    # Get current stock count to include in response
    current_stock = (await (await db.execute(
        "SELECT stock_qty FROM products WHERE id = ?", (product_id,)
    )).fetchone())[0]

    result = get_response(
        "stock_added", lang,
        quantity=_fmt(quantity), unit=unit, product=product, price_note=price_note,
    )
    # Show total stock count
    if lang == "pidgin":
        result = result.rstrip() + f" You get {_fmt(current_stock)} {unit} now."
    else:
        result = result.rstrip() + f" You now have {_fmt(current_stock)} {unit}."
    if supplier_note:
        result = result.rstrip() + supplier_note

    # Supplier price comparison: compare with previous purchase of the same product
    if cost_price > 0:
        cursor = await db.execute(
            """SELECT cost_price, supplier FROM stock_entries
               WHERE phone = ? AND product_id = ? AND cost_price > 0
               ORDER BY id DESC LIMIT 1 OFFSET 1""",
            (phone, product_id))
        prev = await cursor.fetchone()
        if prev and prev[0] > 0 and prev[0] != cost_price:
            diff = cost_price - prev[0]
            pct = int(abs(diff) / prev[0] * 100)
            prev_supplier = prev[1] or "your previous purchase"
            if diff > 0:
                if lang == "pidgin":
                    result += f"\nThis one cost {_fmt(diff)} more than {prev_supplier} ({_fmt(prev[0])}/each, +{pct}%)."
                else:
                    result += f"\nThat's {_fmt(diff)} more than {prev_supplier} ({_fmt(prev[0])}/each, +{pct}%)."
            else:
                if lang == "pidgin":
                    result += f"\nYou save {_fmt(abs(diff))} compared to {prev_supplier} ({_fmt(prev[0])}/each, -{pct}%)."
                else:
                    result += f"\nYou're saving {_fmt(abs(diff))} vs {prev_supplier} ({_fmt(prev[0])}/each, -{pct}%)."

    # One contextual nudge — if no selling price is set, that's the natural next step
    sell_price = (await (await db.execute(
        "SELECT sell_price FROM products WHERE id = ?", (product_id,)
    )).fetchone())[0]
    product_entries = (await (await db.execute(
        "SELECT COUNT(*) FROM stock_entries WHERE phone = ? AND product_id = ?",
        (phone, product_id),
    )).fetchone())[0]
    # Only hint about sell price if no sell_price AND no previous sales with a price
    has_sale_price = False
    if not sell_price:
        has_sale_price = (await (await db.execute(
            "SELECT COUNT(*) FROM sales WHERE phone = ? AND product_id = ? AND unit_price > 0",
            (phone, product_id)
        )).fetchone())[0] > 0
    if not sell_price and not has_sale_price and product_entries <= 2:
        result += get_response("hint_set_price", lang, product=product, unit=unit)
        # Save pending so a bare number reply sets the price
        await _save_pending(db, phone, {
            "action": "set_price_pending",
            "product": product,
            "product_id": product_id,
            "unit": unit,
            "lang": lang,
        })
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
    amount = float(data.get("amount") or 0)
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
    amount = float(data.get("amount") or 0)

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
    payment_amount = float(data.get("payment_amount") or 0)
    credit_amount = float(data.get("credit_amount") or 0)
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
            if row[0] <= 0:
                if lang == "pidgin":
                    return f"You no get {product} for stock. You fit restock am."
                return f"No {product} in stock. You may want to restock."
            return get_response(
                "stock_check_single", lang,
                quantity=_fmt(row[0]), unit=row[1], product=product,
            )
        return get_response("stock_empty", lang)

    cursor = await db.execute(
        "SELECT name, stock_qty, unit, sell_price FROM products WHERE phone = ? AND name NOT LIKE '(general sales)%' AND name NOT LIKE 'daily total%' ORDER BY name",
        (phone,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return get_response("stock_empty", lang)

    # Group products if 8+ items (helps high-volume shops)
    if len(rows) >= 8:
        # Split into stocked (qty > 0), low (0 < qty <= 5), out/negative
        stocked = [r for r in rows if r[1] > 5]
        low = [r for r in rows if 0 < r[1] <= 5]
        out = [r for r in rows if r[1] <= 0]

        parts = []
        if stocked:
            lines = "\n".join(
                f"  {r[0]}: {_fmt(r[1])} {r[2]}" + (f" @ {_fmt(r[3])} ea" if r[3] else "")
                for r in stocked)
            parts.append(f"In stock:\n{lines}")
        if low:
            lines = "\n".join(f"  {r[0]}: {_fmt(r[1])} {r[2]}" for r in low)
            label = "Low stock (restock soon):" if lang == "english" else "Stock dey low:"
            parts.append(f"{label}\n{lines}")
        if out:
            lines = "\n".join(f"  {r[0]}: {_fmt(r[1])} {r[2]}" for r in out)
            label = "Out of stock:" if lang == "english" else "Don finish:"
            parts.append(f"{label}\n{lines}")

        stock_list = "\n\n".join(parts)
    else:
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
    amount = float(data.get("amount") or 0)
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
    """Show individual sales for a period, optionally filtered by product."""
    db = await get_db()
    period = data.get("period", "today")
    product_filter = data.get("product")

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

    params = [phone]
    product_clause = ""
    if product_filter:
        product_filter = _normalize_product_name(product_filter)
        product_clause = " AND LOWER(product_name) = LOWER(?)"
        params.append(product_filter)

    cursor = await db.execute(
        f"""SELECT product_name, quantity, unit_price, total, created_at
           FROM sales WHERE phone = ? AND {date_filter}{product_clause}
           ORDER BY created_at DESC""",
        params,
    )
    rows = await cursor.fetchall()

    product_label = f" {product_filter}" if product_filter else ""

    if not rows:
        if lang == "pidgin":
            return f"You never sell{product_label} {period_text}."
        return f"No{product_label} sales {period_text}."

    total = sum(r[3] for r in rows)
    sales_lines = []
    for r in rows:
        time_str = r[4][11:16] if r[4] and len(r[4]) > 15 else ""
        line = f"  {r[0]} x{_fmt(r[1])} = {_fmt(r[3])} naira"
        if time_str == "00:00":
            line += "  (added later)"
        elif time_str:
            line += f"  ({time_str})"
        sales_lines.append(line)

    sales_list = "\n".join(sales_lines)

    if lang == "pidgin":
        return f"Wetin you sell{product_label} {period_text}:\n{sales_list}\n\nTotal: {_fmt(total)} naira ({len(rows)} sales)"
    return f"Your{product_label} sales {period_text}:\n{sales_list}\n\nTotal: {_fmt(total)} naira ({len(rows)} sales)"


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
    elif period == "all":
        date_filter = "1=1"
        period_label = "All time" if lang == "english" else "All time"
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

    # Credit collection rate (monthly/all only, when credits exist)
    if period in ("month", "all") and credit_total > 0:
        collection_pct = int(payment_total / credit_total * 100) if credit_total > 0 else 0
        nudge = ""
        if collection_pct < 50:
            nudge = ' Try "remind [name]" to send reminders.' if lang == "english" else ' Try "remind [name]" to collect.'
        if lang == "pidgin":
            result += f"\nCredit collection: {collection_pct}% ({_fmt(payment_total)} collected out of {_fmt(credit_total)} given).{nudge}"
        else:
            result += f"\nCredit collection rate: {collection_pct}% ({_fmt(payment_total)} collected of {_fmt(credit_total)} given).{nudge}"

    # Top products (only if more than 1 product sold)
    cursor = await db.execute(
        f"""SELECT product_name, SUM(quantity), SUM(total) FROM sales
           WHERE phone = ? AND {date_filter}
           AND product_name NOT LIKE 'daily total%' AND product_name != '(general sales)'
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
    elif cost_of_goods == 0 and expense_total > 0 and sales_total > 0:
        # No stock cost data — show simpler label for food vendors etc.
        gain = sales_total - expense_total
        if lang == "pidgin":
            result += f"\nWetin remain after expenses: {_fmt(gain)} naira."
        else:
            result += f"\nAfter expenses: {_fmt(gain)} naira."

    # Simple insight: compare with the previous period (revenue + profit)
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

        # Profit trend: compare profit if cost data exists for both periods
        if cost_of_goods > 0:
            prev_profit_filter = prev_filter.replace("created_at", "s.created_at")
            cursor = await db.execute(
                f"""SELECT COALESCE(SUM(s.quantity * p.cost_price), 0)
                    FROM sales s JOIN products p ON s.product_id = p.id
                    WHERE s.phone = ? AND {prev_profit_filter} AND p.cost_price > 0""",
                (phone,),
            )
            prev_cogs = (await cursor.fetchone())[0]
            cursor = await db.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE phone = ? AND {prev_filter}",
                (phone,),
            )
            prev_expenses = (await cursor.fetchone())[0]
            if prev_total > 0 and prev_cogs > 0:
                prev_profit = prev_total - prev_cogs - prev_expenses
                if prev_profit > 0:
                    if profit > prev_profit:
                        pct = int((profit - prev_profit) / prev_profit * 100)
                        if lang == "pidgin":
                            result += f"\nYour gain don go up {pct}% compared to {prev_label.lower()}!"
                        else:
                            result += f"\nYour profit is up {pct}% compared to {prev_label.lower()}!"
                    else:
                        pct = int((prev_profit - profit) / prev_profit * 100)
                        if lang == "pidgin":
                            result += f"\nYour gain don drop {pct}% compared to {prev_label.lower()}."
                        else:
                            result += f"\nYour profit is down {pct}% compared to {prev_label.lower()}."

    # One follow-on insight — pick the most relevant, never stack
    follow_on = ""

    # Margin alert: if monthly summary has COGS and margin dropped vs last month
    if not follow_on and period == "month" and cost_of_goods > 0 and sales_total > 0:
        current_margin = int((sales_total - cost_of_goods) / sales_total * 100)
        prev_month_filter = ("created_at >= datetime('now', '+1 hours', '-60 days') "
                             "AND created_at < datetime('now', '+1 hours', '-30 days')")
        prev_m_filter = prev_month_filter.replace("created_at", "s.created_at")
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND {prev_month_filter}",
            (phone,))
        prev_rev = (await cursor.fetchone())[0]
        if prev_rev > 0:
            cursor = await db.execute(
                f"""SELECT COALESCE(SUM(s.quantity * p.cost_price), 0)
                    FROM sales s JOIN products p ON s.product_id = p.id
                    WHERE s.phone = ? AND {prev_m_filter} AND p.cost_price > 0""",
                (phone,))
            prev_cogs_m = (await cursor.fetchone())[0]
            if prev_cogs_m > 0:
                prev_margin = int((prev_rev - prev_cogs_m) / prev_rev * 100)
                if prev_margin - current_margin >= 5:
                    follow_on = get_response("insight_margin_drop", lang,
                                             old_margin=prev_margin, new_margin=current_margin)

    # Best day insight (weekly/monthly, needs 3+ days of data)
    if not follow_on and period in ("week", "month") and sales_count >= 5:
        day_filter = date_filter.replace("created_at", "created_at")
        cursor = await db.execute(
            f"""SELECT CASE CAST(strftime('%w', created_at) AS INTEGER)
                    WHEN 0 THEN 'Sunday' WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday' WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday' END as day_name,
                SUM(total) as day_total
                FROM sales WHERE phone = ? AND {date_filter}
                GROUP BY strftime('%w', created_at)
                HAVING COUNT(*) >= 2
                ORDER BY day_total DESC LIMIT 1""",
            (phone,),
        )
        best_day = await cursor.fetchone()
        if best_day:
            follow_on = get_response("insight_best_day", lang,
                                     day=best_day[0], total=_fmt(best_day[1]))

    # Customer concentration (monthly/all, needs customer data)
    if not follow_on and period in ("month", "all") and sales_count >= 10:
        cursor = await db.execute(
            f"""SELECT customer, SUM(total) FROM sales
                WHERE phone = ? AND {date_filter} AND customer IS NOT NULL AND customer != ''
                GROUP BY LOWER(customer) ORDER BY SUM(total) DESC LIMIT 1""",
            (phone,),
        )
        top_cust = await cursor.fetchone()
        if top_cust and sales_total > 0:
            cust_pct = int(top_cust[1] / sales_total * 100)
            if cust_pct >= 25:
                follow_on = get_response("insight_customer_concentration", lang,
                                         customer=top_cust[0], total=_fmt(top_cust[1]), pct=cust_pct)

    # Seasonal pattern: compare this month's top product to same month last year
    if not follow_on and period == "month":
        cursor = await db.execute(
            """SELECT MIN(created_at) FROM sales WHERE phone = ?""", (phone,))
        first_sale = await cursor.fetchone()
        if first_sale and first_sale[0]:
            days_since_first = (await (await db.execute(
                "SELECT CAST(julianday('now', '+1 hours') - julianday(?) AS INTEGER)",
                (first_sale[0],))).fetchone())[0]
            if days_since_first >= 90:
                # User has 3+ months of data — check for seasonal patterns
                cursor = await db.execute(
                    """SELECT p.name, SUM(s.quantity) as qty FROM sales s
                       JOIN products p ON s.product_id = p.id
                       WHERE s.phone = ?
                       AND strftime('%%m', s.created_at) = strftime('%%m', 'now', '+1 hours')
                       AND s.created_at < datetime('now', '+1 hours', '-60 days')
                       GROUP BY p.name ORDER BY qty DESC LIMIT 1""",
                    (phone,))
                past_top = await cursor.fetchone()
                if past_top:
                    cursor = await db.execute(
                        f"""SELECT COALESCE(SUM(s.quantity), 0) FROM sales s
                           JOIN products p ON s.product_id = p.id
                           WHERE s.phone = ? AND {date_filter} AND p.name = ?""",
                        (phone, past_top[0]))
                    current_qty = (await cursor.fetchone())[0]
                    if past_top[1] > 0 and current_qty > 0:
                        ratio = current_qty / past_top[1]
                        if ratio >= 1.5:
                            if lang == "pidgin":
                                follow_on = f"\n{past_top[0]} dey sell well this time of year! You don sell {int(ratio)}x more than before."
                            else:
                                follow_on = f"\n{past_top[0]} sells well this time of year! You're selling {int(ratio)}x more than before."

    # Report hint (fallback: only if no other insight fired and user hasn't opened report)
    if not follow_on:
        token_row = await (await db.execute(
            "SELECT token FROM report_tokens WHERE phone = ?", (phone,)
        )).fetchone()
        if not token_row:
            follow_on = get_response("hint_report", lang)

    result += follow_on
    return result


async def handle_set_price(phone: str, data: dict, lang: str) -> str:
    db = await get_db()
    product = data.get("product", "item").lower()
    unit = data.get("unit") or "piece"
    sell_price = float(data.get("sell_price") or 0)

    product_id = await _get_or_create_product(db, phone, product, unit, sell_price)

    # Get old price before updating
    old_price_row = await (await db.execute(
        "SELECT sell_price FROM products WHERE id = ?", (product_id,)
    )).fetchone()
    old_price = old_price_row[0] if old_price_row and old_price_row[0] else 0

    await db.execute(
        "UPDATE products SET sell_price = ? WHERE id = ?",
        (sell_price, product_id),
    )
    await db.commit()

    result = get_response(
        "price_set", lang,
        product=product, price=_fmt(sell_price), unit=unit,
    )

    # Price change impact: show projected impact based on recent sales volume
    if old_price > 0 and old_price != sell_price:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(quantity), 0) FROM sales
               WHERE phone = ? AND product_id = ?
               AND created_at >= datetime('now', '+1 hours', '-30 days')""",
            (phone, product_id))
        monthly_qty = (await cursor.fetchone())[0]
        if monthly_qty > 0:
            diff = sell_price - old_price
            monthly_impact = int(diff * monthly_qty)
            if diff > 0:
                if lang == "pidgin":
                    result += f"\nYou increase am by {_fmt(diff)} from {_fmt(old_price)}. If you sell the same amount, you go make {_fmt(monthly_impact)} more this month."
                else:
                    result += f"\nUp {_fmt(diff)} from {_fmt(old_price)}. At your current volume, that's {_fmt(monthly_impact)} more per month."
            else:
                if lang == "pidgin":
                    result += f"\nYou reduce am by {_fmt(abs(diff))} from {_fmt(old_price)}. That na {_fmt(abs(monthly_impact))} less per month at same volume."
                else:
                    result += f"\nDown {_fmt(abs(diff))} from {_fmt(old_price)}. That's {_fmt(abs(monthly_impact))} less per month at current volume."

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
    """Send the shop's private shareable report link with a voice-friendly summary."""
    from app.config import BASE_URL
    from app.report import get_or_create_report_token

    db = await get_db()
    token = await get_or_create_report_token(phone)
    base = BASE_URL.rstrip('/')
    url = f"{base}/report/{token}"
    export_url = f"{base}/export/{token}"
    result = get_response("report_link", lang, url=url)

    # No shop name yet? The natural next step is to put one on the report.
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


async def handle_set_nudge_time(phone: str, data: dict, lang: str) -> str:
    """Set the user's preferred evening nudge hour (0-23)."""
    db = await get_db()
    hour = data.get("hour")
    if hour is None:
        if lang == "pidgin":
            return "Wetin time you wan get your evening summary? Tell me like \"send my nudge at 7pm\"."
        return "What time do you want your evening summary? Tell me like \"send my nudge at 7pm\"."

    hour = int(hour) % 24
    await db.execute("UPDATE shops SET nudge_hour = ? WHERE phone = ?", (hour, phone))
    await db.commit()

    # Format hour for display
    if hour == 0:
        time_str = "12am"
    elif hour < 12:
        time_str = f"{hour}am"
    elif hour == 12:
        time_str = "12pm"
    else:
        time_str = f"{hour - 12}pm"

    if lang == "pidgin":
        return f"Okay! I go send your evening summary by {time_str} every day."
    return f"Got it! I'll send your evening summary at {time_str} every day."


async def handle_set_goal(phone: str, data: dict, lang: str) -> str:
    """Set a weekly sales goal."""
    db = await get_db()
    amount = data.get("amount")
    if not amount:
        if lang == "pidgin":
            return "How much you wan sell this week? Tell me like \"my goal na 50 thousand\"."
        return "How much do you want to sell this week? Tell me like \"my goal is 50 thousand\"."

    amount = float(amount)
    await db.execute(
        "UPDATE shops SET weekly_goal = ?, weekly_goal_set_at = datetime('now', '+1 hours') WHERE phone = ?",
        (amount, phone))
    await db.commit()

    if lang == "pidgin":
        return f"Goal set! You wan sell {_fmt(amount)} naira this week. I go track am for you."
    return f"Goal set! Target: {_fmt(amount)} naira this week. I'll track your progress."


async def handle_feedback(phone: str, data: dict, lang: str) -> str:
    """Store tester feedback/complaints so the team can review them."""
    db = await get_db()
    message = (data.get("message") or "").strip()

    if not message:
        # Save pending so the NEXT message is captured as feedback
        await _save_pending(db, phone, {
            "action": "pending_feedback",
            "lang": lang,
        })
        if lang == "pidgin":
            return "Wetin happen? Tell me the problem, I go send am to the Tijah team."
        return "What happened? Tell me the problem and I'll send it to the Tijah team."

    await db.execute(
        "INSERT INTO feedback (phone, message) VALUES (?, ?)",
        (phone, message),
    )
    await db.commit()
    return get_response("feedback_saved", lang, message=message)


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
    new_amount = float(data.get("new_amount") or 0)

    if not customer or not new_amount:
        if lang == "pidgin":
            return "Tell me the name and correct amount. Like: \"Mama Joy owes 5 thousand not 8\""
        return "Tell me the name and correct amount. Like: \"Mama Joy owes 5 thousand not 8\""

    matched, match_type = await _find_similar_customer(db, phone, customer)
    if match_type:
        customer = matched

    old_amount = float(data.get("old_amount") or 0)

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

    return reminder


async def handle_confirm_yes(phone: str, data: dict, lang: str) -> str:
    """User confirmed the fuzzy customer match."""
    db = await get_db()
    pending = await _get_pending(db, phone)
    if not pending:
        return ""  # Nothing to confirm — stay silent

    # Long voice confirmation: user says the transcription is correct — process it
    if pending.get("action") == "long_voice_confirm":
        return "__replay__:" + pending["text"]

    # Clarify intent: user confirmed our guess — execute the guessed intent
    if pending.get("action") == "clarify_intent":
        guessed = pending.get("guessed_intent", {})
        guessed.pop("clarify", None)
        guessed_action = guessed.get("action", "help")
        # Import _route_intent to re-route the confirmed intent
        from app.main import _route_intent
        return await _route_intent(phone, guessed, pending.get("lang", lang))

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
        return ""  # Nothing to confirm — stay silent

    # Long voice confirmation: user says transcription was wrong — ask to resend
    if pending.get("action") == "long_voice_confirm":
        if lang == "pidgin":
            return "No wahala. Send another shorter voice note and I go try again."
        return "No problem. Send a shorter voice note and I'll try again."

    # Clarify intent: user rejected our guess — ask them to try again
    if pending.get("action") == "clarify_intent":
        if lang == "pidgin":
            return "No wahala. Try tell me again wetin you wan do."
        return "No problem. Try telling me again what you'd like to do."

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
    """Undo/delete: always show what will be deleted and ask for confirmation."""
    db = await get_db()

    product_filter = data.get("product")
    if product_filter:
        product_filter = _normalize_product_name(product_filter)

    # Expense-specific filters
    desc_filter = data.get("description")
    amount_filter = float(data.get("amount") or 0)

    # Time filter
    when_filter = data.get("when")
    when_date = None
    if when_filter and when_filter != "today":
        resolved = _resolve_when(when_filter)
        if resolved:
            when_date = resolved[:10]

    return await _show_delete_list(db, phone, product_filter, when_date, lang,
                                   desc_filter=desc_filter, amount_filter=amount_filter)


async def _show_delete_list(db, phone, product_filter, when_date, lang,
                            desc_filter=None, amount_filter=0):
    """Show numbered list of recent entries for selective deletion.
    If filters narrow to exactly 1 entry, skip the list and go straight to confirmation."""
    entries = []
    search_tables = [
        ("sales", "product_name", "total"),
        ("stock_entries", "product_name", "cost_price"),
        ("expenses", "description", "amount"),
    ]

    for table, desc_col, amt_col in search_tables:
        where = "phone = ?"
        params = [phone]
        if product_filter and table != "expenses":
            where += f" AND LOWER({desc_col}) LIKE ?"
            params.append(f"%{product_filter}%")
        # Expense-specific filters
        if desc_filter and table == "expenses":
            where += f" AND LOWER({desc_col}) LIKE ?"
            params.append(f"%{desc_filter.lower()}%")
        if amount_filter and table == "expenses":
            where += f" AND {amt_col} = ?"
            params.append(amount_filter)
        if when_date:
            where += " AND date(created_at) = ?"
            params.append(when_date)
        # If we have expense-specific filters, skip non-expense tables
        if (desc_filter or amount_filter) and table != "expenses":
            continue
        cursor = await db.execute(
            f"SELECT id, {desc_col}, {amt_col}, created_at, quantity FROM {table} "
            f"WHERE {where} ORDER BY created_at DESC LIMIT 10"
            if table != "expenses" else
            f"SELECT id, {desc_col}, {amt_col}, created_at, 1 FROM {table} "
            f"WHERE {where} ORDER BY created_at DESC LIMIT 10",
            tuple(params),
        )
        rows = await cursor.fetchall()
        label_map = {"sales": "sale", "stock_entries": "stock", "expenses": "expense"}
        for r in rows:
            entries.append({
                "table": table, "id": r[0], "desc": r[1],
                "amount": r[2], "date": r[3][:10] if r[3] else "",
                "qty": r[4], "label": label_map[table],
            })

    if not entries:
        if lang == "pidgin":
            return "Nothing to delete. You never record anything yet."
        return "Nothing to delete. You haven't recorded anything yet."

    # Sort by date desc, then id desc
    entries.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    entries = entries[:10]

    # If exactly 1 match or no filters (meaning "cancel that" = last entry),
    # go straight to confirmation
    no_filters = not product_filter and not when_date and not desc_filter and not amount_filter
    if len(entries) == 1 or no_filters:
        # Pick the most recent entry
        chosen = entries[0]
        await _save_pending(db, phone, {
            "action": "delete_confirm",
            "entry": chosen,
            "lang": lang,
        })
        desc = chosen["desc"]
        amt = _fmt(chosen["amount"])
        if lang == "pidgin":
            return f"You wan delete this {chosen['label']}: {desc} ({amt} naira)?\n\nSay \"yes\" to delete or \"no\" to cancel."
        return f"Delete this {chosen['label']}: {desc} ({amt} naira)?\n\nSay \"yes\" to delete or \"no\" to cancel."

    # Multiple matches — show numbered list
    lines = []
    filter_desc = product_filter or desc_filter or ""
    if filter_desc:
        if lang == "pidgin":
            lines.append(f"Which {filter_desc} record you wan delete?")
        else:
            lines.append(f"Which {filter_desc} entry do you want to delete?")
    else:
        if lang == "pidgin":
            lines.append("Which record you wan delete?")
        else:
            lines.append("Which entry do you want to delete?")

    for i, e in enumerate(entries, 1):
        if e["label"] == "expense":
            lines.append(f"  {i}. {e['label']}: {e['desc']} = {_fmt(e['amount'])} naira ({e['date']})")
        else:
            lines.append(f"  {i}. {e['label']}: {_fmt(e['qty'])} x {e['desc']} = {_fmt(e['amount'])} naira ({e['date']})")

    if lang == "pidgin":
        lines.append("\nTell me the number. Say \"cancel\" if you no wan delete anything.")
    else:
        lines.append("\nTell me the number. Say \"cancel\" if you don't want to delete.")

    await _save_pending(db, phone, {
        "action": "delete_pick",
        "entries": entries,
        "lang": lang,
    })

    return "\n".join(lines)


async def _find_latest_entry(db, phone, product_filter, when_date):
    """Find the most recent entry across all tables."""
    tables = [
        ("sales", "product_name", "total", "quantity", "product_id"),
        ("expenses", "description", "amount", None, None),
        ("credits", "customer", "amount", None, None),
        ("payments", "customer", "amount", None, None),
        ("stock_entries", "product_name", "cost_price", "quantity", "product_id"),
    ]

    latest = None
    latest_table = None

    for table, desc_col, amount_col, qty_col, pid_col in tables:
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
            + f" FROM {table} WHERE {where} ORDER BY created_at DESC, id DESC LIMIT 1",
            tuple(params),
        )
        row = await cursor.fetchone()
        if row:
            if latest is None or row[3] > latest[3] or (row[3] == latest[3] and row[0] > latest[0]):
                latest = row
                latest_table = table

    return latest, latest_table


async def _delete_entry(db, phone, entry, table, lang):
    """Delete a specific entry and restore related data."""
    entry_id = entry[0]
    desc = entry[1]
    amount = _fmt(entry[2]) if entry[2] else ""

    has_qty = len(entry) > 4
    if table == "sales" and has_qty:
        qty, pid = entry[4], entry[5]
        if pid:
            await db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (qty, pid))
    elif table == "stock_entries" and has_qty:
        qty, pid = entry[4], entry[5]
        if pid:
            await db.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?", (qty, pid))
    elif table == "payments":
        pay_customer = entry[1]
        pay_amount = entry[2]
        remaining_refund = pay_amount
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

    await db.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
    await db.commit()

    labels = {"sales": "sale", "expenses": "expense", "credits": "credit", "payments": "payment", "stock_entries": "stock"}
    label = labels.get(table, "record")

    if lang == "pidgin":
        return f"I don remove the {label}: {desc} ({amount} naira)"
    return f"Removed {label}: {desc} ({amount} naira)"


async def handle_multi_stock(phone: str, data: dict, lang: str) -> str:
    """Handle restocking multiple products in one message."""
    db = await get_db()
    items = data.get("items", [])
    if not items:
        return get_response("not_understood", lang)

    # Top-level supplier applies to all items unless individual items override
    top_supplier = (data.get("supplier") or "").strip() or None

    results = []
    total_cost = 0
    for item in items:
        product = (item.get("product", "item")).lower()
        quantity = float(item.get("quantity", 1))
        unit = item.get("unit") or "piece"
        cost_price = float(item.get("cost_price", 0))
        supplier = (item.get("supplier") or "").strip() or top_supplier

        product_id = await _get_or_create_product(db, phone, product, unit, 0, cost_price)

        await db.execute(
            "UPDATE products SET stock_qty = stock_qty + ?, cost_price = CASE WHEN ? > 0 THEN ? ELSE cost_price END WHERE id = ?",
            (quantity, cost_price, cost_price, product_id),
        )
        await db.execute(
            """INSERT INTO stock_entries (phone, product_id, product_name, quantity, cost_price, entry_type, supplier)
               VALUES (?, ?, ?, ?, ?, 'purchase', ?)""",
            (phone, product_id, product, quantity, cost_price, supplier),
        )

        line = f"  {_fmt(quantity)} {unit} {product}"
        if cost_price > 0:
            item_total = cost_price * quantity
            line += f" ({_fmt(item_total)} naira)"
            total_cost += item_total
        results.append(line)

    await db.commit()

    stock_list = "\n".join(results)
    cost_note = f"\n\nTotal cost: {_fmt(total_cost)} naira" if total_cost > 0 else ""
    supplier_note = f"\nSupplier: {top_supplier}" if top_supplier else ""
    if lang == "pidgin":
        return f"Stock added!\n{stock_list}{cost_note}{supplier_note}"
    return f"Stock added!\n{stock_list}{cost_note}{supplier_note}"


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


async def handle_product_profit(phone: str, data: dict, lang: str) -> str:
    """Show per-product profitability — margin for each product with cost data."""
    db = await get_db()
    period = data.get("period", "month")

    # Build date filter
    date_filters = {
        "today": "date(s.created_at) = date('now', '+1 hours')",
        "yesterday": "date(s.created_at) = date('now', '+1 hours', '-1 day')",
        "week": "s.created_at >= datetime('now', '+1 hours', '-7 days')",
        "month": "s.created_at >= datetime('now', '+1 hours', '-30 days')",
        "all": "1=1",
    }
    date_filter = date_filters.get(period, date_filters["month"])

    cursor = await db.execute(
        f"""SELECT p.name, SUM(s.total) as revenue,
               SUM(s.quantity * p.cost_price) as cost,
               SUM(s.quantity) as qty
           FROM sales s JOIN products p ON s.product_id = p.id
           WHERE s.phone = ? AND {date_filter} AND p.cost_price > 0
           GROUP BY p.name ORDER BY (SUM(s.total) - SUM(s.quantity * p.cost_price)) DESC""",
        (phone,),
    )
    rows = await cursor.fetchall()

    if not rows:
        if lang == "pidgin":
            return "I no get cost data to calculate profit. Tell me how much you buy your stock, like \"I buy 10 bag rice, 3 thousand each\"."
        return "I don't have cost data to calculate profit. Tell me your stock costs, like \"I bought 10 bags of rice at 3 thousand each\"."

    period_labels = {"today": "Today", "yesterday": "Yesterday", "week": "This week", "month": "This month", "all": "All time"}
    label = period_labels.get(period, "This month")

    lines = []
    best_margin_name = ""
    best_margin_pct = -1
    best_revenue_name = ""
    best_revenue_val = 0
    for name, revenue, cost, qty in rows:
        profit = revenue - cost
        margin = int((profit / revenue) * 100) if revenue > 0 else 0
        lines.append(f"  {name}: {_fmt(profit)} naira profit ({margin}% margin)")
        if margin > best_margin_pct:
            best_margin_pct = margin
            best_margin_name = name
        if revenue > best_revenue_val:
            best_revenue_val = revenue
            best_revenue_name = name

    product_list = "\n".join(lines)
    result = f"{label} profit per product:\n{product_list}"

    # Highlight best margin product if it differs from highest revenue
    if len(rows) > 1 and best_margin_name and best_margin_name != best_revenue_name:
        if lang == "pidgin":
            result += f"\n\n{best_margin_name} get the best margin ({best_margin_pct}%). Na your real money-maker!"
        else:
            result += f"\n\n{best_margin_name} has the best margin ({best_margin_pct}%). That's your real money-maker!"

    return result


async def handle_split_product(phone: str, data: dict, lang: str) -> str:
    """Split entries from one product into a new product name."""
    db = await get_db()
    original = _normalize_product_name(data.get("original", ""))
    new_name = _normalize_product_name(data.get("new_name", ""))

    if not original or not new_name:
        if lang == "pidgin":
            return "Tell me like: \"separate jollof rice from rice\""
        return "Tell me like: \"separate jollof rice from rice\""

    # Find the original product
    orig_product = await _find_product(db, phone, original)
    if not orig_product:
        if lang == "pidgin":
            return f"I no see \"{original}\" for your products."
        return f"I can't find \"{original}\" in your products."

    # Create the new product
    new_id = await _get_or_create_product(db, phone, new_name, "piece", orig_product[2])

    # Move sales and stock entries that match the new name
    # Check for sales whose product_name matches the new_name (case-insensitive)
    moved_sales = 0
    cursor = await db.execute(
        "SELECT id FROM sales WHERE phone = ? AND product_id = ? AND LOWER(product_name) LIKE ?",
        (phone, orig_product[0], f"%{new_name}%"),
    )
    for row in await cursor.fetchall():
        await db.execute("UPDATE sales SET product_id = ?, product_name = ? WHERE id = ?",
                         (new_id, new_name, row[0]))
        moved_sales += 1

    # Move stock entries similarly
    cursor = await db.execute(
        "SELECT id FROM stock_entries WHERE phone = ? AND product_id = ? AND LOWER(product_name) LIKE ?",
        (phone, orig_product[0], f"%{new_name}%"),
    )
    for row in await cursor.fetchall():
        await db.execute("UPDATE stock_entries SET product_id = ?, product_name = ? WHERE id = ?",
                         (new_id, new_name, row[0]))

    await db.commit()

    if lang == "pidgin":
        if moved_sales > 0:
            return f"I don separate \"{new_name}\" from \"{original}\". {moved_sales} sale(s) moved."
        return f"I don create \"{new_name}\" as separate product. No old sales to move — new sales go record under \"{new_name}\"."
    if moved_sales > 0:
        return f"Split \"{new_name}\" from \"{original}\". {moved_sales} sale(s) moved."
    return f"Created \"{new_name}\" as a separate product. No old sales to move — new sales will be recorded under \"{new_name}\"."


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
    # Whisper transcription variants
    "fry rice": "fried rice", "frying rice": "fried rice",
    "suya meat": "suya",
    "jollof": "jollof rice",
    "egussi": "egusi", "egushi": "egusi",
    "ogbono": "ogbono",
    "stock fish": "stockfish", "stork fish": "stockfish",
    "puff puff": "puff-puff", "pof pof": "puff-puff",
    "chin chin": "chin-chin",
    "palm oil": "palm oil",
    # Industry-specific: auto parts
    "auto nator": "alternator", "alternata": "alternator",
    "shoka bsorber": "shock absorber", "shock absorba": "shock absorber",
    "shocka": "shock absorber",
    "ball joint": "ball joint",
    "brake pad": "brake pad", "break pad": "brake pad",
    "spark plug": "spark plug", "spark pluck": "spark plug",
    "fan belt": "fan belt", "fanbelt": "fan belt",
    # Building materials
    "iron rod": "iron rod", "iron rode": "iron rod",
    "binding wire": "binding wire",
    # Cosmetics / hair
    "relaxer": "relaxer", "relaxa": "relaxer",
    "hair cream": "hair cream",
    "body cream": "body cream",
    "ankara": "ankara", "anakara": "ankara",
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

    # Extract numeric qualifiers (digits, fractions like 1/2) from search term
    search_nums = set(re.findall(r'\d+/\d+|\d+', name.lower()))

    for r in rows:
        stored = r[1].lower()
        # Search term is a whole word inside stored name
        if pattern.search(stored):
            # If both have numeric qualifiers, they must match to avoid
            # confusing variants like "1/2 inch rod" vs "3/4 inch rod"
            stored_nums = set(re.findall(r'\d+/\d+|\d+', stored))
            if search_nums and stored_nums and search_nums != stored_nums:
                continue
            return r
        # Stored name is a whole word inside search term (guard against short names like "oil" matching "groundnut oil")
        if len(stored) >= 4:
            stored_pattern = re.compile(r'\b' + re.escape(stored) + r'\b')
            if stored_pattern.search(name.lower()):
                stored_nums = set(re.findall(r'\d+/\d+|\d+', stored))
                if search_nums and stored_nums and search_nums != stored_nums:
                    continue
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
        # Sequence-based similarity (positional, not just character overlap)
        from difflib import SequenceMatcher
        if len(name_lower) >= 4 and len(existing_lower) >= 4:
            ratio = SequenceMatcher(None, name_lower, existing_lower).ratio()
            if ratio >= 0.65:
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
    total = float(data.get("total") or 0)
    if total <= 0:
        if lang == "pidgin":
            return "How much you sell? Tell me the amount."
        return "How much did you sell? Tell me the amount."

    when = _resolve_when(data.get("when", "today"))
    # Use date-stamped name so each bulk sale is identifiable
    from datetime import datetime, timedelta
    now_wat = datetime.utcnow() + timedelta(hours=1)
    date_label = now_wat.strftime("%d %b")  # e.g. "06 Aug"
    product_name = f"daily total ({date_label})"
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
    # Growth features for established users
    if sale_count >= 20:
        tips.append('"Compare months"' if is_pidgin else '"Compare months" — track growth')
    if sale_count >= 15 and stock_count > 0:
        tips.append('"Profit per product"' if is_pidgin else '"Profit per product" — find your money-maker')
    if credit_count >= 2:
        cursor = await db.execute(
            "SELECT customer FROM credits WHERE phone = ? AND settled = 0 LIMIT 1", (phone,))
        cust = await cursor.fetchone()
        if cust:
            tips.append(f'"Remind {cust[0]}"' if is_pidgin else f'"Remind {cust[0]}" — send debt reminder')
    if sale_count >= 10:
        tips.append('"My goal na 50 thousand"' if is_pidgin else '"My goal is 50 thousand" — set weekly target')

    if not tips:
        return get_response("help", lang)

    header = "Here na some things I fit do for you:" if is_pidgin else "Here are some things I can do for you:"
    tip_list = "\n".join(f"- {t}" for t in tips[:7])  # Max 7 tips
    footer = "\nJust yarn to me normal!" if is_pidgin else "\nJust talk to me normally!"

    return f"{header}\n\n{tip_list}{footer}"


_SALE_MILESTONES = [25, 50, 100, 200, 500]
_REVENUE_MILESTONES = [100_000, 500_000, 1_000_000, 5_000_000]


async def _check_milestone(db, phone, sale_count, sale_total, lang):
    """Check if this sale crossed a milestone. Returns message or None.
    Each milestone fires only once (tracked in shops.milestones_seen JSON)."""
    cursor = await db.execute("SELECT milestones_seen FROM shops WHERE phone = ?", (phone,))
    row = await cursor.fetchone()
    try:
        seen = json.loads(row[0]) if row and row[0] else []
    except (json.JSONDecodeError, TypeError):
        seen = []

    # Check sale count milestones
    for m in _SALE_MILESTONES:
        if sale_count >= m and f"sales_{m}" not in seen:
            seen.append(f"sales_{m}")
            await db.execute("UPDATE shops SET milestones_seen = ? WHERE phone = ?",
                             (json.dumps(seen), phone))
            await db.commit()
            return get_response("milestone_sales", lang, count=f"{m:,}")

    # Check revenue milestones (only after 10+ sales — don't fire on first big sale)
    if sale_count < 10:
        return None
    cursor = await db.execute(
        "SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ?", (phone,))
    total_rev = (await cursor.fetchone())[0]
    for m in _REVENUE_MILESTONES:
        if total_rev >= m and f"rev_{m}" not in seen:
            seen.append(f"rev_{m}")
            await db.execute("UPDATE shops SET milestones_seen = ? WHERE phone = ?",
                             (json.dumps(seen), phone))
            await db.commit()
            return get_response("milestone_revenue", lang, amount=_fmt(m))

    return None


async def _get_sale_micro_insight(db, phone, product, product_id, lang):
    """Return a lightweight business insight to attach to a sale confirmation.

    Rotates through insight types to avoid repetition. Only fires every 10 sales
    after 30 total, keeping messages lean for cost efficiency.
    """
    sale_count = (await (await db.execute(
        "SELECT COUNT(*) FROM sales WHERE phone = ?", (phone,)
    )).fetchone())[0]

    # Rotate insight type based on sale count
    insight_type = (sale_count // 10) % 3

    if insight_type == 0:
        # Stock velocity: how fast current product is selling
        cursor = await db.execute(
            """SELECT stock_qty, unit FROM products WHERE id = ? AND stock_qty > 0""",
            (product_id,))
        stock_row = await cursor.fetchone()
        if stock_row and stock_row[0] > 0:
            cursor = await db.execute(
                """SELECT COALESCE(SUM(quantity), 0) FROM sales
                   WHERE phone = ? AND product_id = ?
                   AND created_at >= datetime('now', '+1 hours', '-7 days')""",
                (phone, product_id))
            weekly_qty = (await cursor.fetchone())[0]
            if weekly_qty > 0:
                days_left = int(stock_row[0] / (weekly_qty / 7)) if weekly_qty > 0 else 0
                if 0 < days_left <= 7:
                    if lang == "pidgin":
                        return f"\n{product} stock go finish in about {days_left} day{'s' if days_left != 1 else ''}."
                    return f"\nAt this pace, your {product} stock will last about {days_left} day{'s' if days_left != 1 else ''}."

    elif insight_type == 1:
        # Revenue pace: how this month compares to target
        cursor = await db.execute(
            """SELECT COALESCE(SUM(total), 0) FROM sales
               WHERE phone = ? AND created_at >= datetime('now', '+1 hours', 'start of month')""",
            (phone,))
        month_total = (await cursor.fetchone())[0]
        if month_total > 0:
            from datetime import datetime, timedelta
            now = datetime.utcnow() + timedelta(hours=1)
            day_of_month = now.day
            if day_of_month >= 5:
                daily_avg = month_total / day_of_month
                projected = int(daily_avg * 30)
                if lang == "pidgin":
                    return f"\nThis month so far: {_fmt(month_total)} naira. If you keep am up, you fit reach {_fmt(projected)} by month end."
                return f"\nThis month so far: {_fmt(month_total)} naira. On pace for {_fmt(projected)} by month end."

    elif insight_type == 2:
        # Top product comparison
        cursor = await db.execute(
            """SELECT p.name, COALESCE(SUM(s.total), 0) as rev FROM sales s
               JOIN products p ON s.product_id = p.id
               WHERE s.phone = ? AND s.created_at >= datetime('now', '+1 hours', '-30 days')
               GROUP BY p.name ORDER BY rev DESC LIMIT 1""",
            (phone,))
        top = await cursor.fetchone()
        if top and top[0] != product and top[1] > 0:
            if lang == "pidgin":
                return f"\nYour biggest money maker this month na {top[0]} ({_fmt(top[1])} naira)."
            return f"\nYour top seller this month is {top[0]} ({_fmt(top[1])} naira)."

    return ""


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


async def handle_customer_sales(phone: str, data: dict, lang: str) -> str:
    """Show total purchases by a specific customer (cash + credit)."""
    db = await get_db()
    customer = data.get("customer", "").strip()
    if not customer:
        if lang == "pidgin":
            return "Which customer you wan check? Tell me like \"how much Mama Joy buy from me?\""
        return "Which customer? Tell me like \"how much has Mama Joy bought from me?\""

    period = data.get("period", "all")
    if period == "week":
        date_filter = "AND s.created_at >= datetime('now', '+1 hours', '-7 days')"
        period_label = "this week"
    elif period == "month":
        date_filter = "AND s.created_at >= datetime('now', '+1 hours', '-30 days')"
        period_label = "this month"
    elif period == "today":
        date_filter = "AND date(s.created_at) = date('now', '+1 hours')"
        period_label = "today"
    else:
        date_filter = ""
        period_label = "all time"

    # Find customer (fuzzy match)
    customer_match = await _find_similar_customer(db, phone, customer)
    if customer_match:
        matched_name, match_type = customer_match
        if match_type == "exact":
            customer = matched_name

    # Total sales to this customer
    cursor = await db.execute(
        f"""SELECT COUNT(*), COALESCE(SUM(s.total), 0)
            FROM sales s
            WHERE s.phone = ? AND LOWER(s.customer) = LOWER(?) {date_filter}""",
        (phone, customer),
    )
    row = await cursor.fetchone()
    sale_count, sale_total = int(row[0]), row[1]

    # Top products bought
    cursor = await db.execute(
        f"""SELECT s.product_name, SUM(s.quantity), SUM(s.total)
            FROM sales s
            WHERE s.phone = ? AND LOWER(s.customer) = LOWER(?) {date_filter}
            GROUP BY s.product_name ORDER BY SUM(s.total) DESC LIMIT 5""",
        (phone, customer),
    )
    products = await cursor.fetchall()

    # Outstanding credit
    cursor = await db.execute(
        "SELECT COALESCE(SUM(amount - paid), 0) FROM credits WHERE phone = ? AND LOWER(customer) = LOWER(?) AND settled = 0",
        (phone, customer),
    )
    outstanding = (await cursor.fetchone())[0]

    if sale_count == 0 and outstanding == 0:
        if lang == "pidgin":
            return f"I no see any record for {customer}."
        return f"No records found for {customer}."

    # Build response
    if lang == "pidgin":
        result = f"{customer} ({period_label}):\n"
    else:
        result = f"{customer} ({period_label}):\n"

    if sale_count > 0:
        result += f"  Total purchases: {_fmt(sale_total)} naira ({sale_count} transactions)\n"
        if products:
            result += "  Products:\n"
            for p in products:
                result += f"    {p[0]}: {_fmt(p[1])} units = {_fmt(p[2])} naira\n"

    if outstanding > 0:
        result += f"  Outstanding credit: {_fmt(outstanding)} naira"

    return result.rstrip()


async def handle_compare_months(phone: str, data: dict, lang: str) -> str:
    """Side-by-side comparison of this month vs last month."""
    db = await get_db()

    this_month = "created_at >= datetime('now', '+1 hours', 'start of month')"
    last_month = "created_at >= datetime('now', '+1 hours', 'start of month', '-1 month') AND created_at < datetime('now', '+1 hours', 'start of month')"

    async def _period_stats(date_filter):
        cursor = await db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND {date_filter}",
            (phone,),
        )
        row = await cursor.fetchone()
        sales_count, sales_total = int(row[0]), row[1]

        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE phone = ? AND {date_filter}",
            (phone,),
        )
        expenses = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM credits WHERE phone = ? AND {date_filter}",
            (phone,),
        )
        credits = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM payments WHERE phone = ? AND {date_filter}",
            (phone,),
        )
        payments = (await cursor.fetchone())[0]

        return {
            "sales_count": sales_count,
            "sales_total": sales_total,
            "expenses": expenses,
            "credits": credits,
            "payments": payments,
        }

    this = await _period_stats(this_month)
    last = await _period_stats(last_month)

    if this["sales_count"] == 0 and last["sales_count"] == 0:
        return get_response("no_activity", lang)

    # No last month data — can't compare
    if last["sales_count"] == 0 and last["expenses"] == 0:
        if lang == "pidgin":
            return f"This month you sell {_fmt(this['sales_total'])} naira ({this['sales_count']} sales). No data from last month to compare. Keep recording and check again next month!"
        return f"This month you sold {_fmt(this['sales_total'])} naira ({this['sales_count']} sales). No data from last month to compare. Keep recording and check again next month!"

    def _arrow(current, previous):
        if previous == 0:
            return ""
        pct = ((current - previous) / previous) * 100
        if pct > 0:
            return f" (+{pct:.0f}%)"
        elif pct < 0:
            return f" ({pct:.0f}%)"
        return " (same)"

    result = "This month vs Last month:\n\n"
    result += f"Sales: {_fmt(this['sales_total'])} naira vs {_fmt(last['sales_total'])} naira{_arrow(this['sales_total'], last['sales_total'])}\n"
    result += f"Transactions: {this['sales_count']} vs {last['sales_count']}{_arrow(this['sales_count'], last['sales_count'])}\n"

    if this["expenses"] > 0 or last["expenses"] > 0:
        result += f"Expenses: {_fmt(this['expenses'])} naira vs {_fmt(last['expenses'])} naira{_arrow(this['expenses'], last['expenses'])}\n"

    if this["credits"] > 0 or last["credits"] > 0:
        result += f"Credit given: {_fmt(this['credits'])} naira vs {_fmt(last['credits'])} naira\n"

    if this["payments"] > 0 or last["payments"] > 0:
        result += f"Payments received: {_fmt(this['payments'])} naira vs {_fmt(last['payments'])} naira\n"

    # Net cash flow
    this_net = this["sales_total"] - this["credits"] + this["payments"] - this["expenses"]
    last_net = last["sales_total"] - last["credits"] + last["payments"] - last["expenses"]
    result += f"\nNet cash: {_fmt(this_net)} naira vs {_fmt(last_net)} naira{_arrow(this_net, last_net)}"

    return result
