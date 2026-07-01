"""
PostgreSQL-Datenbankverbindung via asyncpg.
"""
import os
import ssl
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Globaler Connection Pool
pool: asyncpg.Pool | None = None

# SSL-Kontext für Supabase
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


CREATE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    asin            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    brand           TEXT DEFAULT '',
    image_url       TEXT DEFAULT '',
    category        TEXT DEFAULT 'Sonstiges',
    current_price   REAL,
    original_price  REAL,
    all_time_low    REAL,
    avg_price       REAL,
    avg90_price     REAL DEFAULT 0,
    avg180_price    REAL DEFAULT 0,
    deal_score      INTEGER DEFAULT 0,
    rating          REAL DEFAULT 0,
    reviews         INTEGER DEFAULT 0,
    prime           INTEGER DEFAULT 1,
    last_updated    TIMESTAMP,
    last_checked    TIMESTAMP,
    affiliate_url   TEXT DEFAULT '',
    is_active       BOOLEAN DEFAULT true,
    is_top_pick     BOOLEAN DEFAULT false,
    is_backup       BOOLEAN DEFAULT false,
    is_fba          BOOLEAN DEFAULT false,
    sales_rank      INTEGER DEFAULT 0,
    tag             TEXT DEFAULT '',
    score_breakdown TEXT DEFAULT ''
)
"""

MIGRATE_PRODUCTS = [
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS last_deep_sync    TIMESTAMP",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS telegram_posted  TIMESTAMP",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS avg90_price   REAL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS avg180_price  REAL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS last_checked  TIMESTAMP",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active     BOOLEAN DEFAULT true",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_top_pick   BOOLEAN DEFAULT false",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_backup     BOOLEAN DEFAULT false",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_fba        BOOLEAN DEFAULT false",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS sales_rank    INTEGER DEFAULT 0",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS tag           TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS score_breakdown TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_volatile   BOOLEAN DEFAULT false",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS first_seen    TIMESTAMP",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS mastodon_posted TIMESTAMP",
]

CREATE_PRICE_HISTORY = """
CREATE TABLE IF NOT EXISTS price_history (
    id        SERIAL PRIMARY KEY,
    asin      TEXT NOT NULL REFERENCES products(asin) ON DELETE CASCADE,
    price     REAL NOT NULL,
    timestamp TEXT NOT NULL
)
"""


async def create_pool() -> asyncpg.Pool:
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=3,
        ssl=ssl_ctx,
    )
    return pool


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        await create_pool()
    return pool


CREATE_INDEXES = [
    # Alle Queries filtern zuerst nach is_active=true — partial indexes sind deutlich schneller
    "CREATE INDEX IF NOT EXISTS idx_active_score   ON products(deal_score DESC) WHERE is_active = true",
    "CREATE INDEX IF NOT EXISTS idx_active_price   ON products(current_price)   WHERE is_active = true",
    "CREATE INDEX IF NOT EXISTS idx_active_updated ON products(last_updated DESC) WHERE is_active = true",
    "CREATE INDEX IF NOT EXISTS idx_active_cat     ON products(category)        WHERE is_active = true",
    "CREATE INDEX IF NOT EXISTS idx_price_history_asin ON price_history(asin)",
]

async def init_db():
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute(CREATE_PRODUCTS)
        await conn.execute(CREATE_PRICE_HISTORY)
        for stmt in MIGRATE_PRODUCTS:
            try:
                await conn.execute(stmt)
            except Exception:
                pass  # Spalte existiert bereits
        for stmt in CREATE_INDEXES:
            try:
                await conn.execute(stmt)
            except Exception:
                pass  # Index existiert bereits
    print("Datenbank initialisiert.")
