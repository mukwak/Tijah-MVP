import re
from typing import Any

import aiosqlite

from app.config import DATABASE_URL, DB_PATH

try:
    import asyncpg
except ImportError:  # pragma: no cover - only needed for hosted Postgres
    asyncpg = None


TIMEZONE_OFFSET = "+01:00"
_db = None


class QueryResult:
    def __init__(self, rows: list[Any] | None = None, lastrowid: int | None = None):
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class SQLiteDatabase:
    backend = "sqlite"

    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.init_tables()

    async def execute(self, sql: str, params: tuple | list = ()):
        cursor = await self.conn.execute(sql, params)
        return cursor

    async def executescript(self, sql: str):
        await self.conn.executescript(sql)

    async def commit(self):
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def init_tables(self):
        await self.executescript(SQLITE_SCHEMA)
        await self.commit()
        # Migrations for existing databases
        try:
            await self.execute("ALTER TABLE shops ADD COLUMN voice_user INTEGER DEFAULT 0")
            await self.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self.execute("ALTER TABLE shops ADD COLUMN long_voice_hinted INTEGER DEFAULT 0")
            await self.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self.execute("ALTER TABLE shops ADD COLUMN nudge_hour INTEGER DEFAULT 20")
            await self.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self.execute("ALTER TABLE stock_entries ADD COLUMN supplier TEXT")
            await self.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self.execute("ALTER TABLE shops ADD COLUMN milestones_seen TEXT")
            await self.commit()
        except Exception:
            pass  # Column already exists

    async def try_mark_message_processed(self, message_id: str) -> bool:
        if not message_id:
            return False
        cursor = await self.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,),
        )
        await self.commit()
        return cursor.rowcount == 1


class PostgresDatabase:
    backend = "postgres"

    def __init__(self, url: str):
        self.url = url
        self.pool = None

    async def connect(self):
        if asyncpg is None:
            raise RuntimeError("DATABASE_URL is set to Postgres, but asyncpg is not installed")
        # Pool instead of a single connection: Neon suspends idle databases and
        # kills connections, so each acquire must be able to reconnect.
        # statement_cache_size=0 keeps PgBouncer-pooled URLs working too.
        self.pool = await asyncpg.create_pool(
            self.url,
            statement_cache_size=0,
            min_size=0,
            max_size=5,
            max_inactive_connection_lifetime=60,
        )
        await self.init_tables()

    async def execute(self, sql: str, params: tuple | list = ()):
        sql = _translate_sqlite_query(sql)
        sql = _convert_placeholders(sql)
        lowered = sql.lstrip().lower()
        if lowered.startswith("select"):
            rows = await self._fetch(sql, params)
            return QueryResult(rows)
        if " returning " in lowered:
            rows = await self._fetch(sql, params)
            lastrowid = rows[0][0] if rows else None
            return QueryResult(rows, lastrowid=lastrowid)
        await self._execute(sql, params)
        return QueryResult()

    async def _fetch(self, sql: str, params):
        try:
            return await self.pool.fetch(sql, *params)
        except (asyncpg.PostgresConnectionError, ConnectionError, OSError):
            # Stale connection after a Neon suspend - retry once on a fresh one
            return await self.pool.fetch(sql, *params)

    async def _execute(self, sql: str, params):
        try:
            return await self.pool.execute(sql, *params)
        except (asyncpg.PostgresConnectionError, ConnectionError, OSError):
            return await self.pool.execute(sql, *params)

    async def executescript(self, sql: str):
        await self._execute(sql, ())

    async def commit(self):
        return None

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def init_tables(self):
        await self.executescript(POSTGRES_SCHEMA)
        # Migrations for existing databases
        try:
            await self._execute("ALTER TABLE shops ADD COLUMN voice_user INTEGER DEFAULT 0", ())
        except Exception:
            pass  # Column already exists
        try:
            await self._execute("ALTER TABLE shops ADD COLUMN long_voice_hinted INTEGER DEFAULT 0", ())
        except Exception:
            pass  # Column already exists
        try:
            await self._execute("ALTER TABLE shops ADD COLUMN nudge_hour INTEGER DEFAULT 20", ())
        except Exception:
            pass  # Column already exists
        try:
            await self._execute("ALTER TABLE stock_entries ADD COLUMN supplier TEXT", ())
        except Exception:
            pass  # Column already exists
        try:
            await self._execute("ALTER TABLE shops ADD COLUMN milestones_seen TEXT", ())
        except Exception:
            pass  # Column already exists

    async def try_mark_message_processed(self, message_id: str) -> bool:
        if not message_id:
            return False
        rows = await self._fetch(
            """
            INSERT INTO processed_messages (message_id)
            VALUES ($1)
            ON CONFLICT (message_id) DO NOTHING
            RETURNING message_id
            """,
            (message_id,),
        )
        return len(rows) > 0


async def get_db():
    global _db
    if _db is None:
        if DATABASE_URL.startswith(("postgres://", "postgresql://")):
            _db = PostgresDatabase(DATABASE_URL)
        else:
            _db = SQLiteDatabase(DB_PATH)
        await _db.connect()
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_tables(db):
    await db.init_tables()


async def try_mark_message_processed(message_id: str) -> bool:
    db = await get_db()
    return await db.try_mark_message_processed(message_id)


def _convert_placeholders(sql: str) -> str:
    index = 0

    def repl(_match):
        nonlocal index
        index += 1
        return f"${index}"

    return re.sub(r"\?", repl, sql)


def _translate_sqlite_query(sql: str) -> str:
    replacements = {
        "MAX(0, stock_qty - ?)": "GREATEST(0, stock_qty - ?)",
        "INSERT OR IGNORE INTO report_tokens (phone, token) VALUES (?, ?)":
            "INSERT INTO report_tokens (phone, token) VALUES (?, ?) ON CONFLICT (phone) DO NOTHING",
        "INSERT OR IGNORE INTO customer_receipts (phone, customer, token) VALUES (?, ?, ?)":
            "INSERT INTO customer_receipts (phone, customer, token) VALUES (?, ?, ?) ON CONFLICT (phone, customer) DO NOTHING",
        "INSERT OR REPLACE INTO pending_actions (phone, action_data) VALUES (?, ?)":
            "INSERT INTO pending_actions (phone, action_data) VALUES (?, ?) "
            "ON CONFLICT (phone) DO UPDATE SET action_data = EXCLUDED.action_data, "
            "created_at = to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')",
        "datetime('now', '+1 hours')":
            "to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')",
        "datetime('now', '+1 hours', '-7 days')":
            "to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour' - INTERVAL '7 days', 'YYYY-MM-DD HH24:MI:SS')",
        "datetime('now', '+1 hours', '-14 days')":
            "to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour' - INTERVAL '14 days', 'YYYY-MM-DD HH24:MI:SS')",
        "datetime('now', '+1 hours', '-30 days')":
            "to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour' - INTERVAL '30 days', 'YYYY-MM-DD HH24:MI:SS')",
        "datetime('now', '+1 hours', '-60 days')":
            "to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour' - INTERVAL '60 days', 'YYYY-MM-DD HH24:MI:SS')",
        "date('now', '+1 hours')":
            "((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour')::date",
        "date('now', '+1 hours', '-1 day')":
            "((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour' - INTERVAL '1 day')::date",
        "date(created_at)": "created_at::date",
    }
    for old, new in replacements.items():
        sql = sql.replace(old, new)
    if "INSERT INTO products" in sql and "RETURNING id" not in sql:
        sql = sql.rstrip() + " RETURNING id"
    return sql


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    phone       TEXT PRIMARY KEY,
    name        TEXT,
    language    TEXT DEFAULT 'english',
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    onboarded   INTEGER DEFAULT 0,
    voice_user  INTEGER DEFAULT 0,
    long_voice_hinted INTEGER DEFAULT 0,
    nudge_hour  INTEGER DEFAULT 20,
    milestones_seen TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL,
    name        TEXT NOT NULL,
    unit        TEXT DEFAULT 'piece',
    stock_qty   REAL DEFAULT 0,
    cost_price  REAL DEFAULT 0,
    sell_price  REAL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
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
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
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
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    updated_at  TEXT DEFAULT (datetime('now', '+1 hours')),
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
    supplier    TEXT,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL,
    description TEXT NOT NULL,
    amount      REAL NOT NULL,
    category    TEXT DEFAULT 'other',
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone)
);

CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL,
    customer    TEXT NOT NULL,
    amount      REAL NOT NULL,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone)
);

CREATE TABLE IF NOT EXISTS pending_actions (
    phone       TEXT PRIMARY KEY,
    action_data TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone)
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id  TEXT PRIMARY KEY,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours'))
);

CREATE TABLE IF NOT EXISTS report_tokens (
    phone       TEXT PRIMARY KEY,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone)
);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours'))
);

CREATE INDEX IF NOT EXISTS idx_payments_phone ON payments(phone, customer);
CREATE INDEX IF NOT EXISTS idx_sales_phone_date ON sales(phone, created_at);
CREATE INDEX IF NOT EXISTS idx_credits_phone ON credits(phone, customer, settled);
CREATE INDEX IF NOT EXISTS idx_products_phone ON products(phone);
CREATE INDEX IF NOT EXISTS idx_expenses_phone_date ON expenses(phone, created_at);
CREATE INDEX IF NOT EXISTS idx_processed_messages_created ON processed_messages(created_at);

CREATE TABLE IF NOT EXISTS customer_receipts (
    phone       TEXT NOT NULL,
    customer    TEXT NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT DEFAULT (datetime('now', '+1 hours')),
    FOREIGN KEY (phone) REFERENCES shops(phone),
    UNIQUE(phone, customer)
);
"""


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    phone       TEXT PRIMARY KEY,
    name        TEXT,
    language    TEXT DEFAULT 'english',
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS'),
    onboarded   INTEGER DEFAULT 0,
    voice_user  INTEGER DEFAULT 0,
    long_voice_hinted INTEGER DEFAULT 0,
    nudge_hour  INTEGER DEFAULT 20,
    milestones_seen TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    phone       TEXT NOT NULL REFERENCES shops(phone),
    name        TEXT NOT NULL,
    unit        TEXT DEFAULT 'piece',
    stock_qty   DOUBLE PRECISION DEFAULT 0,
    cost_price  DOUBLE PRECISION DEFAULT 0,
    sell_price  DOUBLE PRECISION DEFAULT 0,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS'),
    UNIQUE(phone, name)
);

CREATE TABLE IF NOT EXISTS sales (
    id           SERIAL PRIMARY KEY,
    phone        TEXT NOT NULL REFERENCES shops(phone),
    product_id   INTEGER REFERENCES products(id),
    product_name TEXT NOT NULL,
    quantity     DOUBLE PRECISION NOT NULL,
    unit_price   DOUBLE PRECISION NOT NULL,
    total        DOUBLE PRECISION NOT NULL,
    customer     TEXT,
    is_credit    INTEGER DEFAULT 0,
    created_at   TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS credits (
    id          SERIAL PRIMARY KEY,
    phone       TEXT NOT NULL REFERENCES shops(phone),
    customer    TEXT NOT NULL,
    amount      DOUBLE PRECISION NOT NULL,
    paid        DOUBLE PRECISION DEFAULT 0,
    settled     INTEGER DEFAULT 0,
    note        TEXT,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS'),
    updated_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS stock_entries (
    id           SERIAL PRIMARY KEY,
    phone        TEXT NOT NULL REFERENCES shops(phone),
    product_id   INTEGER REFERENCES products(id),
    product_name TEXT NOT NULL,
    quantity     DOUBLE PRECISION NOT NULL,
    cost_price   DOUBLE PRECISION DEFAULT 0,
    entry_type   TEXT DEFAULT 'purchase',
    supplier     TEXT,
    created_at   TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS expenses (
    id          SERIAL PRIMARY KEY,
    phone       TEXT NOT NULL REFERENCES shops(phone),
    description TEXT NOT NULL,
    amount      DOUBLE PRECISION NOT NULL,
    category    TEXT DEFAULT 'other',
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS payments (
    id          SERIAL PRIMARY KEY,
    phone       TEXT NOT NULL REFERENCES shops(phone),
    customer    TEXT NOT NULL,
    amount      DOUBLE PRECISION NOT NULL,
    note        TEXT,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS pending_actions (
    phone       TEXT PRIMARY KEY REFERENCES shops(phone),
    action_data TEXT NOT NULL,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id  TEXT PRIMARY KEY,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS report_tokens (
    phone       TEXT PRIMARY KEY REFERENCES shops(phone),
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS feedback (
    id          SERIAL PRIMARY KEY,
    phone       TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE INDEX IF NOT EXISTS idx_payments_phone ON payments(phone, customer);
CREATE INDEX IF NOT EXISTS idx_sales_phone_date ON sales(phone, created_at);
CREATE INDEX IF NOT EXISTS idx_credits_phone ON credits(phone, customer, settled);
CREATE INDEX IF NOT EXISTS idx_products_phone ON products(phone);
CREATE INDEX IF NOT EXISTS idx_expenses_phone_date ON expenses(phone, created_at);
CREATE INDEX IF NOT EXISTS idx_processed_messages_created ON processed_messages(created_at);

CREATE TABLE IF NOT EXISTS customer_receipts (
    phone       TEXT NOT NULL REFERENCES shops(phone),
    customer    TEXT NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT DEFAULT to_char((NOW() AT TIME ZONE 'UTC') + INTERVAL '1 hour', 'YYYY-MM-DD HH24:MI:SS'),
    UNIQUE(phone, customer)
);
"""
