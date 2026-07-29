"""Shareable web report: each shop gets a tokenized link showing all their data.
Also handles per-customer receipt pages for credit disputes."""
import html
import secrets

from app.database import get_db


async def get_or_create_report_token(phone: str) -> str:
    """Return the shop's report token, creating one if needed."""
    db = await get_db()
    cursor = await db.execute("SELECT token FROM report_tokens WHERE phone = ?", (phone,))
    row = await cursor.fetchone()
    if row:
        return row[0]
    token = secrets.token_urlsafe(16)
    await db.execute(
        "INSERT OR IGNORE INTO report_tokens (phone, token) VALUES (?, ?)",
        (phone, token),
    )
    await db.commit()
    # Re-read in case of a concurrent insert
    cursor = await db.execute("SELECT token FROM report_tokens WHERE phone = ?", (phone,))
    row = await cursor.fetchone()
    return row[0]


async def get_phone_by_token(token: str) -> str | None:
    db = await get_db()
    cursor = await db.execute("SELECT phone FROM report_tokens WHERE token = ?", (token,))
    row = await cursor.fetchone()
    return row[0] if row else None


# --- Customer receipt tokens ---

async def get_or_create_customer_receipt_token(phone: str, customer: str) -> str:
    """Return a receipt token for a specific customer, creating one if needed."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT token FROM customer_receipts WHERE phone = ? AND LOWER(customer) = LOWER(?)",
        (phone, customer),
    )
    row = await cursor.fetchone()
    if row:
        return row[0]
    token = secrets.token_urlsafe(16)
    await db.execute(
        "INSERT OR IGNORE INTO customer_receipts (phone, customer, token) VALUES (?, ?, ?)",
        (phone, customer, token),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT token FROM customer_receipts WHERE phone = ? AND LOWER(customer) = LOWER(?)",
        (phone, customer),
    )
    row = await cursor.fetchone()
    return row[0]


async def get_customer_by_receipt_token(token: str) -> tuple[str, str] | None:
    """Return (phone, customer) for a receipt token, or None."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT phone, customer FROM customer_receipts WHERE token = ?", (token,)
    )
    row = await cursor.fetchone()
    return (row[0], row[1]) if row else None


def _fmt(num) -> str:
    num = float(num or 0)
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


async def render_admin_html() -> str:
    """Admin overview: every shop's activity plus tester feedback."""
    db = await get_db()

    cursor = await db.execute(
        """SELECT s.phone, s.name, s.language, s.created_at,
                  (SELECT COUNT(*) FROM sales WHERE sales.phone = s.phone),
                  (SELECT COALESCE(SUM(total), 0) FROM sales WHERE sales.phone = s.phone),
                  (SELECT MAX(created_at) FROM sales WHERE sales.phone = s.phone)
           FROM shops s ORDER BY s.created_at DESC""")
    shops = await cursor.fetchall()

    cursor = await db.execute(
        "SELECT phone, message, created_at FROM feedback ORDER BY created_at DESC LIMIT 200")
    feedback = await cursor.fetchall()

    cursor = await db.execute("SELECT COUNT(*) FROM processed_messages")
    msg_count = (await cursor.fetchone())[0]

    shop_rows = "".join(
        f"<tr><td>{_e(s[0])}</td><td>{_e(s[1] or '-')}</td><td>{_e(s[2])}</td>"
        f"<td>{_e(str(s[3])[:10])}</td><td>{s[4]}</td><td>&#8358;{_fmt(s[5])}</td>"
        f"<td>{_e(str(s[6])[:16] if s[6] else 'never')}</td></tr>"
        for s in shops
    ) or '<tr><td colspan="7" class="empty">No shops yet</td></tr>'

    feedback_rows = "".join(
        f"<tr><td>{_e(str(f[2])[:16])}</td><td>{_e(f[0])}</td><td>{_e(f[1])}</td></tr>"
        for f in feedback
    ) or '<tr><td colspan="3" class="empty">No feedback yet</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Tijah Admin</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f5f5f0; color: #222; }}
  header {{ background: #333; color: #fff; padding: 20px 16px; }}
  header h1 {{ margin: 0; font-size: 1.3rem; }}
  section {{ padding: 0 16px 16px; }}
  h2 {{ font-size: 1rem; margin: 16px 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; font-size: 0.85rem; }}
  th {{ background: #eee; text-align: left; padding: 8px; }}
  td {{ padding: 8px; border-top: 1px solid #f0f0f0; }}
  .empty {{ color: #999; text-align: center; }}
</style>
</head>
<body>
<header>
  <h1>Tijah Admin</h1>
  <p>{len(shops)} shops &middot; {msg_count} messages processed</p>
</header>
<section>
  <h2>Shops</h2>
  <table><tr><th>Phone</th><th>Name</th><th>Lang</th><th>Joined</th><th>Sales</th><th>Total</th><th>Last sale</th></tr>{shop_rows}</table>
  <h2>Tester feedback</h2>
  <table><tr><th>Date</th><th>Phone</th><th>Message</th></tr>{feedback_rows}</table>
</section>
</body>
</html>"""


async def render_report_html(phone: str) -> str:
    """Render the full shop report as mobile-friendly HTML."""
    db = await get_db()

    cursor = await db.execute("SELECT name, language, created_at FROM shops WHERE phone = ?", (phone,))
    shop = await cursor.fetchone()
    shop_name = (shop[0] if shop and shop[0] else "My Shop")

    # Totals
    cursor = await db.execute(
        "SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE phone = ?", (phone,))
    total_sales, sales_count = await cursor.fetchone()

    cursor = await db.execute(
        "SELECT COALESCE(SUM(total), 0) FROM sales WHERE phone = ? AND date(created_at) = date('now', '+1 hours')",
        (phone,))
    today_sales = (await cursor.fetchone())[0]

    cursor = await db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE phone = ?", (phone,))
    total_expenses = (await cursor.fetchone())[0]

    cursor = await db.execute(
        "SELECT COALESCE(SUM(amount - paid), 0) FROM credits WHERE phone = ? AND settled = 0",
        (phone,))
    outstanding_credit = (await cursor.fetchone())[0]

    # Detail rows
    cursor = await db.execute(
        """SELECT created_at, product_name, quantity, unit_price, total, customer, is_credit
           FROM sales WHERE phone = ? ORDER BY created_at DESC LIMIT 100""", (phone,))
    sales = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT name, unit, stock_qty, sell_price FROM products
           WHERE phone = ? ORDER BY name""", (phone,))
    products = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT customer, amount, paid, note, created_at FROM credits
           WHERE phone = ? AND settled = 0 ORDER BY created_at DESC""", (phone,))
    credits = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT customer, amount, note, created_at FROM payments
           WHERE phone = ? ORDER BY created_at DESC LIMIT 50""", (phone,))
    payments = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT created_at, description, category, amount FROM expenses
           WHERE phone = ? ORDER BY created_at DESC LIMIT 100""", (phone,))
    expenses = await cursor.fetchall()

    def _date(ts) -> str:
        return _e(str(ts)[:16])

    sales_rows = "".join(
        f"<tr><td>{_date(s[0])}</td><td>{_e(s[1])}</td><td>{_fmt(s[2])}</td>"
        f"<td>&#8358;{_fmt(s[4])}</td><td>{_e(s[5] or '-')}{' (credit)' if s[6] else ''}</td></tr>"
        for s in sales
    ) or '<tr><td colspan="5" class="empty">No sales yet</td></tr>'

    product_rows = "".join(
        f"<tr><td>{_e(p[0])}</td><td>{_fmt(p[2])} {_e(p[1])}</td><td>&#8358;{_fmt(p[3])}</td></tr>"
        for p in products
    ) or '<tr><td colspan="3" class="empty">No products yet</td></tr>'

    credit_rows = "".join(
        f"<tr><td>{_e(c[0])}</td><td>&#8358;{_fmt(c[1])}</td><td>&#8358;{_fmt(c[2])}</td>"
        f"<td>&#8358;{_fmt(float(c[1]) - float(c[2] or 0))}</td><td>{_date(c[4])}</td></tr>"
        for c in credits
    ) or '<tr><td colspan="5" class="empty">Nobody owes you</td></tr>'

    payment_rows = "".join(
        f"<tr><td>{_date(p[3])}</td><td>{_e(p[0])}</td><td>&#8358;{_fmt(p[1])}</td></tr>"
        for p in payments
    ) or '<tr><td colspan="3" class="empty">No payments yet</td></tr>'

    expense_rows = "".join(
        f"<tr><td>{_date(e[0])}</td><td>{_e(e[1])}</td><td>{_e(e[2])}</td><td>&#8358;{_fmt(e[3])}</td></tr>"
        for e in expenses
    ) or '<tr><td colspan="4" class="empty">No expenses yet</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{_e(shop_name)} - Tijah Report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f5f5f0; color: #222; font-size: 16px; }}
  header {{ background: #1a7f4e; color: #fff; padding: 20px 12px; }}
  header h1 {{ margin: 0; font-size: 1.3rem; }}
  header p {{ margin: 4px 0 0; opacity: 0.85; font-size: 0.85rem; }}
  .cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card .label {{ font-size: 0.75rem; color: #777; text-transform: uppercase; }}
  .card .value {{ font-size: 1.2rem; font-weight: 700; margin-top: 4px; }}
  section {{ padding: 0 12px 12px; }}
  h2 {{ font-size: 1rem; margin: 14px 0 8px; }}
  .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; min-width: 320px; }}
  th {{ background: #eee; text-align: left; padding: 8px 6px; white-space: nowrap; }}
  td {{ padding: 8px 6px; border-top: 1px solid #f0f0f0; }}
  .empty {{ color: #999; text-align: center; }}
  footer {{ text-align: center; color: #999; font-size: 0.75rem; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>{_e(shop_name)}</h1>
  <p>Tijah shop report &middot; all amounts in Naira</p>
</header>
<div class="cards">
  <div class="card"><div class="label">Sales today</div><div class="value">&#8358;{_fmt(today_sales)}</div></div>
  <div class="card"><div class="label">Total sales ({sales_count})</div><div class="value">&#8358;{_fmt(total_sales)}</div></div>
  <div class="card"><div class="label">Owed to you</div><div class="value">&#8358;{_fmt(outstanding_credit)}</div></div>
  <div class="card"><div class="label">Total expenses</div><div class="value">&#8358;{_fmt(total_expenses)}</div></div>
</div>
<section>
  <h2>Stock</h2>
  <div class="table-wrap"><table><tr><th>Product</th><th>In stock</th><th>Price</th></tr>{product_rows}</table></div>
  <h2>People who owe you</h2>
  <div class="table-wrap"><table><tr><th>Customer</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Date</th></tr>{credit_rows}</table></div>
  <h2>Recent sales</h2>
  <div class="table-wrap"><table><tr><th>Date</th><th>Product</th><th>Qty</th><th>Total</th><th>Customer</th></tr>{sales_rows}</table></div>
  <h2>Payments received</h2>
  <div class="table-wrap"><table><tr><th>Date</th><th>Customer</th><th>Amount</th></tr>{payment_rows}</table></div>
  <h2>Expenses</h2>
  <div class="table-wrap"><table><tr><th>Date</th><th>Item</th><th>Category</th><th>Amount</th></tr>{expense_rows}</table></div>
</section>
<footer>Powered by Tijah &middot; This link is private to this shop</footer>
</body>
</html>"""


async def render_customer_receipt_html(phone: str, customer: str) -> str:
    """Render a receipt page for a single customer — safe to share with the customer."""
    db = await get_db()

    # Shop name
    cursor = await db.execute("SELECT name FROM shops WHERE phone = ?", (phone,))
    shop = await cursor.fetchone()
    shop_name = (shop[0] if shop and shop[0] else "Shop")

    # All credits for this customer
    cursor = await db.execute(
        """SELECT amount, paid, note, created_at FROM credits
           WHERE phone = ? AND LOWER(customer) = LOWER(?)
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    credits = await cursor.fetchall()

    # All payments from this customer
    cursor = await db.execute(
        """SELECT amount, note, created_at FROM payments
           WHERE phone = ? AND LOWER(customer) = LOWER(?)
           ORDER BY created_at ASC""",
        (phone, customer),
    )
    payments = await cursor.fetchall()

    total_credit = sum(float(c[0]) for c in credits)
    total_paid = sum(float(p[0]) for p in payments)
    balance = total_credit - total_paid

    credit_rows = "".join(
        f"<tr><td>{_e(str(c[3])[:10])}</td><td>{_e(c[2] or '-')}</td>"
        f"<td>&#8358;{_fmt(c[0])}</td></tr>"
        for c in credits
    ) or '<tr><td colspan="3" class="empty">No records</td></tr>'

    payment_rows = "".join(
        f"<tr><td>{_e(str(p[2])[:10])}</td><td>&#8358;{_fmt(p[0])}</td></tr>"
        for p in payments
    ) or '<tr><td colspan="2" class="empty">No payments yet</td></tr>'

    status_color = "#d32f2f" if balance > 0 else "#1a7f4e"
    status_text = f"&#8358;{_fmt(balance)} owing" if balance > 0 else "All cleared"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{_e(customer)} - Receipt from {_e(shop_name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f5f5f0; color: #222; font-size: 16px; }}
  header {{ background: #1a7f4e; color: #fff; padding: 20px 12px; }}
  header h1 {{ margin: 0; font-size: 1.3rem; }}
  header p {{ margin: 4px 0 0; opacity: 0.85; font-size: 0.85rem; }}
  .status {{ margin: 12px; padding: 16px; border-radius: 10px; background: #fff;
             text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .status .amount {{ font-size: 1.5rem; font-weight: 700; color: {status_color}; }}
  .status .label {{ font-size: 0.85rem; color: #777; margin-top: 4px; }}
  .summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 12px; }}
  .summary .card {{ background: #fff; border-radius: 10px; padding: 12px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
  .summary .card .label {{ font-size: 0.7rem; color: #777; text-transform: uppercase; }}
  .summary .card .value {{ font-size: 1.1rem; font-weight: 700; margin-top: 4px; }}
  section {{ padding: 0 12px 12px; }}
  h2 {{ font-size: 1rem; margin: 14px 0 8px; }}
  .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }}
  th {{ background: #eee; text-align: left; padding: 8px 6px; white-space: nowrap; }}
  td {{ padding: 8px 6px; border-top: 1px solid #f0f0f0; }}
  .empty {{ color: #999; text-align: center; }}
  footer {{ text-align: center; color: #999; font-size: 0.75rem; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>{_e(shop_name)}</h1>
  <p>Receipt for {_e(customer)}</p>
</header>
<div class="status">
  <div class="amount">{status_text}</div>
  <div class="label">Current balance</div>
</div>
<div class="summary">
  <div class="card"><div class="label">Total bought</div><div class="value">&#8358;{_fmt(total_credit)}</div></div>
  <div class="card"><div class="label">Total paid</div><div class="value">&#8358;{_fmt(total_paid)}</div></div>
</div>
<section>
  <h2>Items bought</h2>
  <div class="table-wrap"><table><tr><th>Date</th><th>Item</th><th>Amount</th></tr>{credit_rows}</table></div>
  <h2>Payments made</h2>
  <div class="table-wrap"><table><tr><th>Date</th><th>Amount</th></tr>{payment_rows}</table></div>
</section>
<footer>Powered by Tijah &middot; {_e(shop_name)}</footer>
</body>
</html>"""
