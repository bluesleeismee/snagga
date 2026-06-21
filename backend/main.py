"""
Snagga — FastAPI Backend
Endpoints: GET /deals  GET /product/{asin}  GET /categories  POST /refresh
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from database import DB_PATH, init_db
from scraper import fetch_and_update_deals, generate_history
from scheduler import create_scheduler

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

class Product(BaseModel):
    asin: str
    name: str
    brand: str
    image_url: str
    category: str
    current_price: float
    original_price: float
    all_time_low: float
    avg_price: float
    deal_score: int
    rating: float
    reviews: int
    prime: bool
    last_updated: str
    affiliate_url: str
    price_history: list[float] = []


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Beim ersten Start: DB befüllen wenn leer
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM products")).fetchone()
        count = row[0] if row else 0

    if count == 0:
        print("Datenbank leer — lade initiale Daten …")
        await fetch_and_update_deals()

    # Scheduler starten
    scheduler = create_scheduler()
    scheduler.start()
    print(f"Scheduler aktiv — tägliches Update um {os.getenv('SCHEDULER_HOUR','3')}:0{os.getenv('SCHEDULER_MINUTE','0')} Uhr")

    yield

    scheduler.shutdown()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Snagga API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: Zeile → Product
# ---------------------------------------------------------------------------

async def row_to_product(row, db: aiosqlite.Connection, history_limit: int = 30) -> Product:
    asin = row[0]
    rows = await (await db.execute(
        "SELECT price FROM price_history WHERE asin=? ORDER BY timestamp DESC LIMIT ?",
        (asin, history_limit),
    )).fetchall()
    prices = [r[0] for r in reversed(rows)]
    if not prices:
        prices = generate_history(asin, row[5], row[8])
        prices = [p for p, _ in prices[-30:]]

    return Product(
        asin=row[0], name=row[1], brand=row[2], image_url=row[3], category=row[4],
        current_price=row[5], original_price=row[6], all_time_low=row[7],
        avg_price=row[8], deal_score=row[9], rating=row[10], reviews=row[11],
        prime=bool(row[12]), last_updated=row[13], affiliate_url=row[14],
        price_history=prices,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/deals", response_model=list[Product])
async def get_deals(
    category: Optional[str] = Query(None),
    sort_by:  str           = Query("score", pattern="^(score|discount|price_asc|price_desc|newest)$"),
    limit:    int           = Query(50, ge=1, le=200),
    search:   Optional[str] = Query(None),
):
    """Gibt gefilterte und sortierte Deal-Liste zurück."""
    sort_map = {
        "score":      "deal_score DESC",
        "discount":   "(1.0 - current_price / original_price) DESC",
        "price_asc":  "current_price ASC",
        "price_desc": "current_price DESC",
        "newest":     "last_updated DESC",
    }
    order = sort_map.get(sort_by, "deal_score DESC")

    where_clauses = []
    params: list = []

    if category and category != "Alle":
        where_clauses.append("category = ?")
        params.append(category)

    if search:
        where_clauses.append("(LOWER(name) LIKE ? OR LOWER(brand) LIKE ?)")
        s = f"%{search.lower()}%"
        params.extend([s, s])

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT * FROM products {where} ORDER BY {order} LIMIT ?", params
        )).fetchall()
        return [await row_to_product(r, db) for r in rows]


@app.get("/product/{asin}", response_model=Product)
async def get_product(asin: str):
    """Gibt ein einzelnes Produkt mit voller Preishistorie zurück."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT * FROM products WHERE asin=?", (asin,)
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        return await row_to_product(row, db, history_limit=180)


@app.get("/categories", response_model=list[str])
async def get_categories():
    """Gibt alle vorhandenen Kategorien zurück."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT DISTINCT category FROM products ORDER BY category"
        )).fetchall()
    cats = [r[0] for r in rows if r[0]]
    return ["Alle"] + cats


@app.post("/refresh")
async def refresh_deals():
    """Manuelles Refresh der Deal-Daten (für Testing)."""
    count = await fetch_and_update_deals()
    return {"message": f"{count} Produkte aktualisiert"}


@app.get("/health")
async def health():
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM products")).fetchone()
    return {"status": "ok", "products": row[0] if row else 0