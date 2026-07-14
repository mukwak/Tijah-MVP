"""Shareable web report: each shop gets a tokenized link showing all their data."""
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


def _fmt(num) -> str:
    num = float(num or 0)
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.1f}"


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


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
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f5f5f0; color: #222; }}
  header {{ background: #1a7f4e; color: #fff; padding: 20px 16px; }}
  header h1 {{ margin: 0; font-size: 1.3rem; }}
  header p {{ margin: 4px 0 0; opacity: 0.85; font-size: 0.85rem; }}
  .cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 16px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card .label {{ font-size: 0.75rem; color: #777; text-transform: uppercase; }}
  .card .value {{ font-size: 1.25rem; font-weight: 700; margin-top: 4px; }}
  section {{ padding: 0 16px 16px; }}
  h2 {{ font-size: 1rem; margin: 12px 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; font-size: 0.85rem; }}
  th {{ background: #eee; text-align: left; padding: 8px; }}
  td {{ padding: 8px; border-top: 1px solid #f0f0f0; }}
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
  <table><tr><th>Product</th><th>In stock</th><th>Price</th></tr>{product_rows}</table>
  <h2>People who owe you</h2>
  <table><tr><th>Customer</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Date</th></tr>{credit_rows}</table>
  <h2>Recent sales</h2>
  <table><tr><th>Date</th><th>Product</th><th>Qty</th><th>Total</th><th>Customer</th></tr>{sales_rows}</table>
  <h2>Payments received</h2>
  <table><tr><th>Date</th><th>Customer</th><th>Amount</th></tr>{payment_rows}</table>
  <h2>Expenses</h2>
  <table><tr><th>Date</th><th>Item</th><th>Category</th><th>Amount</th></tr>{expense_rows}</table>
</section>
<footer>Powered by Tijah &middot; This link is private to this shop</footer>
</body>
</html>"""
