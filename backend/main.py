"""
Snagga — FastAPI Backend
Endpoints: GET /deals  GET /product/{asin}  GET /categories  POST /refresh
"""
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from database import get_pool, init_db
from scraper import fetch_and_update_deals, generate_history
from scheduler import create_scheduler

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Rate-Limiting für /refresh (manuell, kein externes Paket)
_last_refresh: float = 0
REFRESH_COOLDOWN = 300  # 5 Minuten


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

    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM products")

    if count == 0:
        print("Datenbank leer — lade initiale Daten …")
        await fetch_and_update_deals()

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
    allow_origins=[
        "https://snagga.de",
        "https://www.snagga.de",
        "http://localhost:5173",
        "http://localhost:3000",
        FRONTEND_URL,
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: Zeile → Product
# ---------------------------------------------------------------------------

async def row_to_product(row, conn, history_limit: int = 30) -> Product:
    asin = row["asin"]
    ph_rows = await conn.fetch(
        "SELECT price FROM price_history WHERE asin=$1 ORDER BY timestamp DESC LIMIT $2",
        asin, history_limit,
    )
    prices = [r["price"] for r in reversed(ph_rows)]
    if not prices:
        prices = generate_history(asin, row["current_price"], row["avg_price"])
        prices = [p for p, _ in prices[-30:]]

    return Product(
        asin=row["asin"], name=row["name"], brand=row["brand"],
        image_url=row["image_url"], category=row["category"],
        current_price=row["current_price"], original_price=row["original_price"],
        all_time_low=row["all_time_low"], avg_price=row["avg_price"],
        deal_score=row["deal_score"], rating=row["rating"], reviews=row["reviews"],
        prime=bool(row["prime"]), last_updated=row["last_updated"],
        affiliate_url=row["affiliate_url"],
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
    sort_map = {
        "score":      "deal_score DESC",
        "discount":   "(1.0 - current_price / original_price) DESC",
        "price_asc":  "current_price ASC",
        "price_desc": "current_price DESC",
        "newest":     "last_updated DESC",
    }
    order = sort_map.get(sort_by, "deal_score DESC")

    where_clauses: list[str] = []
    params: list = []
    idx = 1

    if category and category != "Alle":
        where_clauses.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    if search:
        where_clauses.append(f"(LOWER(name) LIKE ${idx} OR LOWER(brand) LIKE ${idx+1})")
        s = f"%{search.lower()}%"
        params.extend([s, s])
        idx += 2

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM products {where} ORDER BY {order} LIMIT ${idx}", *params
        )
        return [await row_to_product(r, conn) for r in rows]


@app.get("/product/{asin}", response_model=Product)
async def get_product(asin: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM products WHERE asin=$1", asin)
        if not row:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        return await row_to_product(row, conn, history_limit=180)


@app.get("/categories", response_model=list[str])
async def get_categories():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT category FROM products ORDER BY category")
    cats = [r["category"] for r in rows if r["category"]]
    return ["Alle"] + cats


@app.post("/refresh")
async def refresh_deals():
    """Manuelles Refresh — max. alle 5 Minuten."""
    global _last_refresh
    now = time.time()
    if now - _last_refresh < REFRESH_COOLDOWN:
        wait = int(REFRESH_COOLDOWN - (now - _last_refresh))
        raise HTTPException(status_code=429, detail=f"Bitte {wait}s warten.")
    _last_refresh = now
    count = await fetch_and_update_deals()
    return {"message": f"{count} Produkte aktualisiert"}


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM products")
    return {"status": "ok", "products": count or 0}
