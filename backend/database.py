import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "snagga.db")

CREATE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    asin        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    brand       TEXT DEFAULT '',
    image_url   TEXT DEFAULT '',
    category    TEXT DEFAULT 'Sonstiges',
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
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    asin      TEXT NOT NULL,
    price     REAL NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (asin) REFERENCES products(asin) ON DELETE CASCADE
)
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_PRODUCTS)
        await db.execute(CREATE_PRICE_HISTORY)
        await db.commit()
