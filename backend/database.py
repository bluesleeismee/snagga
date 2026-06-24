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
    deal_score      INTEGER DEFAULT 0,
    rating          REAL DEFAULT 0,
    reviews         INTEGER DEFAULT 0,
    prime           INTEGER DEFAULT 1,
    last_updated    TEXT,
    affiliate_url   TEXT DEFAULT ''
)
"""

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
        max_size=10,
        ssl=ssl_ctx,
    )
    return pool


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        await create_pool()
    return pool


async def init_db():
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute(CREATE_PRODUCTS)
        await conn.execute(CREATE_PRICE_HISTORY)
    print("Datenbank initialisiert.")
