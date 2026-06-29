import aiosqlite
from app.config import DB_PATH

_db = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await init_tables(_db)
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_tables(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS shops (
            phone       TEXT PRIMARY KEY,
            name        TEXT,
            language    TEXT DEFAULT 'english',
            created_at  TEXT DEFAULT (datetime('now')),
            onboarded   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            name        TEXT NOT NULL,
            unit        TEXT DEFAULT 'piece',
            stock_qty   REAL DEFAULT 0,
            cost_price  REAL DEFAULT 0,
            sell_price  REAL DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone),
            UNIQUE(phone, name)
        );

        CREATE TABLE IF NOT EXISTS sales (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            product_id  INTEGER,
            product_name TEXT NOT NULL,
            quantity    REAL NOT NULL,
            unit_price  REAL NOT NULL,
            total       REAL NOT NULL,
            customer    TEXT,
            is_credit   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS credits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            customer    TEXT NOT NULL,
            amount      REAL NOT NULL,
            paid        REAL DEFAULT 0,
            settled     INTEGER DEFAULT 0,
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone)
        );

        CREATE TABLE IF NOT EXISTS stock_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            product_id  INTEGER,
            product_name TEXT NOT NULL,
            quantity    REAL NOT NULL,
            cost_price  REAL DEFAULT 0,
            entry_type  TEXT DEFAULT 'purchase',
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            description TEXT NOT NULL,
            amount      REAL NOT NULL,
            category    TEXT DEFAULT 'other',
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone)
        );

        CREATE TABLE IF NOT EXISTS pending_actions (
            phone       TEXT PRIMARY KEY,
            action_data TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (phone) REFERENCES shops(phone)
        );

        CREATE INDEX IF NOT EXISTS idx_sales_phone_date ON sales(phone, created_at);
        CREATE INDEX IF NOT EXISTS idx_credits_phone ON credits(phone, customer, settled);
        CREATE INDEX IF NOT EXISTS idx_products_phone ON products(phone);
        CREATE INDEX IF NOT EXISTS idx_expenses_phone_date ON expenses(phone, created_at);
    """)
    await db.commit()
