"""
Snagga — FastAPI Backend
Endpoints: GET /deals  GET /product/{asin}  GET /categories  POST /refresh
"""
import html
import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

load_dotenv()

from database import get_pool, init_db
from scraper import fetch_and_update_deals, generate_history
from scheduler import create_scheduler

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ADMIN_TOKEN  = os.getenv("ADMIN_TOKEN", "")

def _check_admin(token: str = Query(default="")):
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# Rate-Limiting für /refresh
_last_refresh: float = 0
REFRESH_COOLDOWN = 300  # 5 Minuten

# In-Memory-Cache
_cache: dict = {}
CACHE_TTL = 300  # 5 Minuten


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None


def cache_set(key: str, data):
    if len(_cache) > 40:
        oldest = min(_cache, key=lambda k: _cache[k]["ts"])
        del _cache[oldest]
    _cache[key] = {"data": data, "ts": time.time()}


def cache_clear():
    _cache.clear()


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

class Product(BaseModel):
    asin:           str
    name:           str
    brand:          str
    image_url:      str
    category:       str
    current_price:  float
    original_price: float
    all_time_low:   float
    avg_price:      float
    deal_score:     int
    rating:         float
    reviews:        int
    prime:          bool
    last_updated:   str
    affiliate_url:  str
    price_history:  list[float] = []
    # Neu
    is_top_pick:    bool = False
    is_fba:         bool = False
    sales_rank:     int  = 0
    tag:            str  = ""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active=true")
        if count == 0:
            print("Datenbank leer — lade initiale Deals via Keepa …")
            await fetch_and_update_deals()
        print(f"Datenbankverbindung OK — {count} aktive Deals.")
    except Exception as e:
        print(f"[WARN] DB-Verbindung beim Start fehlgeschlagen: {e}")
        print("App startet trotzdem -- DB wird beim ersten Request neu versucht.")

    scheduler = create_scheduler()
    scheduler.start()
    print("Scheduler aktiv — stündliche Updates + nächtlicher Deep-Sync 03:00 Uhr")

    yield

    scheduler.shutdown()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Snagga API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://snagga.de",
        "https://www.snagga.de",
        "https://snagga-git-variante-desktop-v2-davidpauli-6139s-projects.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        FRONTEND_URL,
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen: DB-Zeilen → Products
# ---------------------------------------------------------------------------

def _row_to_product(row, prices: list[float]) -> Product:
    return Product(
        asin=row["asin"], name=row["name"], brand=row["brand"],
        image_url=row["image_url"], category=row["category"],
        current_price=row["current_price"], original_price=row["original_price"],
        all_time_low=row["all_time_low"], avg_price=row["avg_price"],
        deal_score=row["deal_score"], rating=row["rating"], reviews=row["reviews"],
        prime=bool(row["prime"]),
        last_updated=str(row["last_updated"]) if row["last_updated"] else "",
        affiliate_url=row["affiliate_url"],
        price_history=prices,
        is_top_pick=bool(row["is_top_pick"]) if "is_top_pick" in row.keys() else False,
        is_fba=bool(row["is_fba"])       if "is_fba"       in row.keys() else False,
        sales_rank=int(row["sales_rank"]) if "sales_rank"   in row.keys() else 0,
        tag=row["tag"]                   if "tag"           in row.keys() else "",
    )


async def rows_to_products(rows, conn, history_limit: int = 30) -> list[Product]:
    """
    Listen-Ansicht — OHNE Preishistorie.

    Das Frontend (DealCard, ProductModal) rendert keinen Preisverlauf, daher wird
    price_history in der Liste NICHT geladen. Bei bis zu 500 Deals würde das sonst
    zehntausende price_history-Zeilen in den RAM ziehen (frühere OOM-Ursache auf
    Render Free 512MB). Die Detailabfrage /product/{asin} lädt bei Bedarf weiterhin
    die volle Historie.
    """
    return [_row_to_product(row, []) for row in rows]


async def row_to_product(row, conn, history_limit: int = 30) -> Product:
    """Einzelner Deal (Detailansicht) — behält eigene Abfrage für history_limit=180."""
    asin = row["asin"]
    ph_rows = await conn.fetch(
        "SELECT price FROM price_history WHERE asin=$1 ORDER BY timestamp DESC LIMIT $2",
        asin, history_limit,
    )
    prices = list(reversed([r["price"] for r in ph_rows]))
    if not prices:
        prices = [p for p, _ in generate_history(asin, row["current_price"], row["avg_price"])[-30:]]
    return _row_to_product(row, prices)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/deals", response_model=list[Product])
async def get_deals(
    category: Optional[str] = Query(None),
    sort_by:  str           = Query("score", pattern="^(score|discount|price_asc|price_desc|newest)$"),
    limit:    int           = Query(60, ge=1, le=600),
    search:   Optional[str] = Query(None),
):
    cache_key = f"deals:{category}:{sort_by}:{limit}:{search}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    sort_map = {
        "score":      "deal_score DESC",
        "discount":   "(1.0 - current_price / NULLIF(original_price,0)) DESC",
        "price_asc":  "current_price ASC",
        "price_desc": "current_price DESC",
        "newest":     "first_seen DESC NULLS LAST, last_updated DESC",
    }
    order = sort_map.get(sort_by, "deal_score DESC")

    where_clauses: list[str] = ["is_active = true"]
    params: list = []
    idx = 1

    if category and category == "Top Picks":
        where_clauses.append("is_top_pick = true")
    elif category and category != "Alle":
        cat_list = [c.strip() for c in category.split('|') if c.strip()]
        if len(cat_list) == 1:
            where_clauses.append(f"category = ${idx}")
            params.append(cat_list[0])
            idx += 1
        elif len(cat_list) > 1:
            placeholders = ','.join(f'${idx + i}' for i in range(len(cat_list)))
            where_clauses.append(f"category IN ({placeholders})")
            params.extend(cat_list)
            idx += len(cat_list)

    if search:
        where_clauses.append(f"(LOWER(name) LIKE ${idx} OR LOWER(brand) LIKE ${idx+1})")
        s = f"%{search.lower()}%"
        params.extend([s, s])
        idx += 2

    where = "WHERE " + " AND ".join(where_clauses)
    params.append(limit)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM products {where} ORDER BY {order} LIMIT ${idx}", *params
        )
        result = await rows_to_products(rows, conn)

    cache_set(cache_key, result)
    return result


@app.get("/product/{asin}", response_model=Product)
async def get_product(asin: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE asin=$1 AND is_active=true", asin
        )
        if not row:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        return await row_to_product(row, conn, history_limit=180)


_ASIN_RE = re.compile(r"^[A-Za-z0-9]{10}$")


@app.get("/share/{asin}", response_class=HTMLResponse)
async def share_deal(asin: str):
    """
    Server-gerenderte Preview für geteilte Deal-Links (Telegram, WhatsApp, native
    Share-Sheets). Crawler/Link-Unfurler lesen nur die statischen OG-Tags unten
    und führen kein JS aus; echte Besucher werden per Meta-Refresh + JS sofort
    zur eigentlichen SPA-Seite mit dem Produkt-Modal weitergeleitet.
    """
    target = "https://snagga.de/"
    if _ASIN_RE.match(asin):
        target = f"https://snagga.de/?asin={asin}"

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name, image_url, current_price, original_price, tag "
                "FROM products WHERE asin=$1", asin,
            )
        if row:
            name     = html.escape((row["name"] or "Deal")[:90])
            current  = row["current_price"]    or 0
            original = row["original_price"]   or 0
            tag      = html.escape(row["tag"] or "")
            price_txt = f"{current:.2f}".replace(".", ",") + " €"
            disc = round((original - current) / original * 100) if original > current else 0

            title = f"{name} — {price_txt}" + (f" (-{disc}%)" if disc > 0 else "")
            original_txt = f"{original:.2f}".replace(".", ",") + " €"
            desc  = f"{tag or 'Deal'} auf snagga.de — statt {original_txt}" if original > current \
                    else "Aktueller Bestpreis auf snagga.de"
            image = html.escape(row["image_url"] or "https://snagga.de/favicon.svg")

            return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<meta http-equiv="refresh" content="0;url={target}">
<meta property="og:type" content="product">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{image}">
<meta property="og:url" content="{target}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{image}">
</head>
<body>
<script>location.replace({target!r});</script>
<p>Weiterleitung zu <a href="{target}">snagga.de</a>…</p>
</body>
</html>""")

    return HTMLResponse(f'<meta http-equiv="refresh" content="0;url={target}">'
                         f'<script>location.replace({target!r})</script>')


@app.get("/deal/{asin}", response_class=HTMLResponse)
async def deal_page(asin: str):
    """
    Eigene, serverseitig gerenderte und crawlbare Detailseite pro Deal.
    Anders als /share: KEIN Redirect. Die React-SPA selbst hat nur eine
    einzige URL (Client-Side-Filterung), Google kann darüber also nie
    einzelne Produkte für Long-Tail-Suchen indexieren. Diese Seite schliesst
    die Lücke — eigene URL, eigener Title/Description, JSON-LD Product-Markup.
    """
    if not _ASIN_RE.match(asin):
        raise HTTPException(status_code=404, detail="Ungültige ASIN")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name, image_url, current_price, original_price, tag, category, "
            "rating, reviews, affiliate_url, is_active FROM products WHERE asin=$1",
            asin,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Deal nicht gefunden")

    canonical = f"https://snagga.de/deal/{asin}"
    name      = html.escape((row["name"] or "Deal")[:200])
    image     = html.escape(row["image_url"] or "https://snagga.de/favicon.svg")
    affiliate = html.escape(row["affiliate_url"] or f"https://www.amazon.de/dp/{asin}")

    # Abgelaufene Deals: Seite bleibt erreichbar (keine toten Links aus Google),
    # aber noindex — verhindert veraltete Preise in den Suchergebnissen.
    if not row["is_active"]:
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>{name} — Deal nicht mehr verfügbar | snagga.de</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="{canonical}">
</head>
<body style="font-family:system-ui,sans-serif;text-align:center;padding:60px 20px;background:#F2EFEA;color:#1F1E1D">
<h1>Dieser Deal ist nicht mehr verfügbar</h1>
<p>{name}</p>
<p><a href="https://snagga.de/">Alle aktuellen Deals ansehen →</a></p>
</body>
</html>""")

    current  = row["current_price"]  or 0
    original = row["original_price"] or 0
    tag      = html.escape(row["tag"] or "")
    category = html.escape(row["category"] or "")
    rating   = row["rating"]  or 0
    reviews  = row["reviews"] or 0
    disc = round((original - current) / original * 100) if original > current else 0
    price_txt    = f"{current:.2f}".replace(".", ",") + " €"
    original_txt = f"{original:.2f}".replace(".", ",") + " €"

    title = f"{name} für {price_txt}" + (f" statt {original_txt} (-{disc}%)" if disc > 0 else "") + " | snagga.de"
    desc  = html.escape(
        (f"{row['tag']} — " if row["tag"] else "") +
        f"{row['name'] or 'Deal'} aktuell für {price_txt} auf snagga.de" +
        (f", {disc}% günstiger als der bisherige Preis." if disc > 0 else ".")
    )

    rating_html = f'<p>⭐ {rating:.1f} ({reviews} Bewertungen)</p>' if rating > 0 and reviews > 0 else ""

    ld_json: dict = {
        "@context":   "https://schema.org/",
        "@type":      "Product",
        "name":       row["name"] or "Deal",
        "image":      [row["image_url"]] if row["image_url"] else [],
        "description": desc,
        "category":   row["category"] or "",
        "offers": {
            "@type":         "Offer",
            "url":           row["affiliate_url"] or affiliate,
            "priceCurrency": "EUR",
            "price":         f"{current:.2f}",
            "availability":  "https://schema.org/InStock",
        },
    }
    if rating > 0 and reviews > 0:
        ld_json["aggregateRating"] = {
            "@type":       "AggregateRating",
            "ratingValue": f"{rating:.1f}",
            "reviewCount": int(reviews),
        }

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="product">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{image}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{json.dumps(ld_json, ensure_ascii=False)}</script>
<style>
  body {{ font-family: system-ui, sans-serif; background:#F2EFEA; color:#1F1E1D; margin:0; }}
  header {{ background:#153D68; padding:16px 20px; }}
  header a {{ color:#EDE9E3; font-size:22px; font-weight:800; text-decoration:none; }}
  main {{ max-width:640px; margin:0 auto; padding:32px 20px; }}
  img {{ max-width:100%; border-radius:8px; }}
  .tag {{ display:inline-block; background:#C85E43; color:#fff; font-size:13px; font-weight:700; padding:4px 10px; border-radius:4px; margin-bottom:12px; }}
  .price {{ font-size:28px; font-weight:800; }}
  .original {{ color:#888; text-decoration:line-through; font-size:16px; margin-left:8px; font-weight:400; }}
  .cta {{ display:inline-block; margin-top:20px; background:#C85E43; color:#fff; padding:14px 28px; border-radius:4px; text-decoration:none; font-weight:700; }}
  .back {{ display:block; margin-top:24px; color:#153D68; }}
</style>
</head>
<body>
<header><a href="https://snagga.de/">snagga.de</a></header>
<main>
  {f'<div class="tag">{tag}</div>' if tag else ''}
  <img src="{image}" alt="{name}">
  <h1>{name}</h1>
  <p class="price">{price_txt}{f'<span class="original">{original_txt}</span>' if disc > 0 else ''}</p>
  {rating_html}
  <p>Kategorie: {category}</p>
  <a class="cta" href="{affiliate}" rel="nofollow sponsored noopener" target="_blank">Zum Angebot bei Amazon →</a>
  <a class="back" href="https://snagga.de/">← Alle Deals ansehen</a>
</main>
</body>
</html>""")


@app.get("/sitemap.xml")
async def sitemap():
    """Dynamische Sitemap — jeder aktive Deal bekommt eine eigene, crawlbare URL."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, last_updated FROM products WHERE is_active=true ORDER BY deal_score DESC"
        )

    urls = [
        "  <url><loc>https://snagga.de/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>",
        "  <url><loc>https://snagga.de/legal</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>",
    ]
    for row in rows:
        lastmod = f"<lastmod>{row['last_updated'].date().isoformat()}</lastmod>" if row["last_updated"] else ""
        urls.append(
            f"  <url><loc>https://snagga.de/deal/{row['asin']}</loc>{lastmod}"
            f"<changefreq>daily</changefreq><priority>0.6</priority></url>"
        )

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    return Response(content=xml, media_type="application/xml")


@app.get("/categories", response_model=list[str])
async def get_categories():
    cached = cache_get("categories")
    if cached is not None:
        return cached
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT category FROM products WHERE is_active=true ORDER BY category"
        )
    cats = ["Alle"] + [r["category"] for r in rows if r["category"]]
    cache_set("categories", cats)
    return cats


@app.post("/refresh")
async def refresh_deals(token: str = Query(default="")):
    """Manuelles Refresh — max. alle 5 Minuten."""
    _check_admin(token)
    global _last_refresh
    now = time.time()
    if now - _last_refresh < REFRESH_COOLDOWN:
        wait = int(REFRESH_COOLDOWN - (now - _last_refresh))
        raise HTTPException(status_code=429, detail=f"Bitte {wait}s warten.")
    _last_refresh = now
    try:
        count = await fetch_and_update_deals()
    except Exception as exc:
        import traceback
        print(f"[REFRESH ERROR] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))
    cache_clear()
    return {"message": f"{count} aktive Deals geladen"}


@app.get("/debug/keepa-cats")
async def debug_keepa_cats(token: str = Query(default="")):
    """Gibt rootCat-Verteilung + avg-Datenverfügbarkeit aus Keepa /deal zurück."""
    _check_admin(token)
    import os, json, httpx
    from collections import Counter
    KEEPA_KEY = os.getenv("KEEPA_API_KEY", "")
    if not KEEPA_KEY:
        return {"error": "no key"}

    sel = json.dumps({"page": 0, "domainId": 3, "priceTypes": 0,
                       "deltaPercentRange": [-100, -10], "dateRange": 0,
                       "minRating": 35, "hasReviews": True,
                       "isFilterEnabled": True, "filterErotic": True})
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.keepa.com/deal",
                              params={"key": KEEPA_KEY, "selection": sel})
        r.raise_for_status()
        data = r.json()

    raw = (data.get("deals") or {}).get("dr") or []
    cat_counts = Counter(d.get("rootCat", 0) for d in raw)
    samples = {}
    for d in raw:
        rc = d.get("rootCat", 0)
        if rc not in samples:
            samples[rc] = d.get("title", "")[:60]

    # avg-Datenverfügbarkeit: welche Perioden und Indizes haben Daten?
    avg_stats = {"any_avg90": 0, "any_avg180": 0, "any_avg365": 0}
    idx_hits = Counter()
    for d in raw:
        avgs = d.get("avg") or []
        for period_i, period_name in [(1, "avg90"), (2, "avg180"), (3, "avg365")]:
            if period_i < len(avgs) and avgs[period_i]:
                arr = avgs[period_i]
                has_data = any(isinstance(v, (int, float)) and v > 0 for v in arr)
                if has_data:
                    avg_stats[f"any_{period_name}"] += 1
                    for i, v in enumerate(arr):
                        if isinstance(v, (int, float)) and v > 0:
                            idx_hits[i] += 1

    # 5 Beispiel-Deals mit avg90-Rohdaten (Indizes 0,1,3,10,16,17,18)
    sample_deals = []
    for d in raw[:10]:
        avgs = d.get("avg") or []
        cur = d.get("current") or []
        avg90_arr = avgs[1] if len(avgs) > 1 else []
        def cv(arr, i): return arr[i] if arr and i < len(arr) and isinstance(arr[i], (int,float)) and arr[i] > 0 else None
        sample_deals.append({
            "asin": d.get("asin"),
            "title": (d.get("title") or "")[:40],
            "rootCat": d.get("rootCat"),
            "cur_0": cv(cur, 0), "cur_18": cv(cur, 18), "cur_10": cv(cur, 10),
            "avg90_0": cv(avg90_arr, 0), "avg90_18": cv(avg90_arr, 18),
            "avg90_1": cv(avg90_arr, 1), "avg90_10": cv(avg90_arr, 10),
            "avg90_16": cv(avg90_arr, 16), "avg90_17": cv(avg90_arr, 17),
        })

    return {
        "total": len(raw),
        "tokens_left": data.get("tokensLeft"),
        "rootcat_counts": dict(cat_counts.most_common(25)),
        "rootcat_samples": samples,
        "avg_data_availability": avg_stats,
        "avg_index_hits_top10": dict(idx_hits.most_common(10)),
        "sample_deals_raw": sample_deals,
    }


@app.get("/debug/category-tree")
async def debug_category_tree(token: str = Query(default="")):
    """Holt den kompletten Amazon-DE-Kategoriebaum von Keepa."""
    _check_admin(token)
    import os, httpx
    KEEPA_KEY = os.getenv("KEEPA_API_KEY", "")
    if not KEEPA_KEY:
        return {"error": "no key"}

    async with httpx.AsyncClient(timeout=30) as client:
        # Erst: alle Root-Kategorien (catId=0)
        r = await client.get("https://api.keepa.com/category",
                             params={"key": KEEPA_KEY, "domain": 3, "category": 0, "parents": 0})
        r.raise_for_status()
        root_data = r.json()

    root_cats = root_data.get("categories", {})

    # Kompakte Ausgabe: id → {name, children}
    tree = {}
    for cat_id, cat in root_cats.items():
        tree[cat_id] = {
            "name": cat.get("name", ""),
            "children": cat.get("children", []),
        }

    return {
        "tokens_left": root_data.get("tokensLeft"),
        "root_category_count": len(tree),
        "categories": tree,
    }


@app.get("/debug/category-children/{cat_id}")
async def debug_category_children(cat_id: int, token: str = Query(default="")):
    """Holt Unterkategorien einer bestimmten Kategorie."""
    _check_admin(token)
    import os, httpx
    KEEPA_KEY = os.getenv("KEEPA_API_KEY", "")
    if not KEEPA_KEY:
        return {"error": "no key"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.keepa.com/category",
                             params={"key": KEEPA_KEY, "domain": 3, "category": cat_id, "parents": 1})
        r.raise_for_status()
        data = r.json()

    cats = data.get("categories", {})
    result = {}
    for cid, cat in cats.items():
        result[cid] = {
            "name": cat.get("name", ""),
            "parent": cat.get("parent", 0),
            "children": cat.get("children", []),
        }

    return {
        "tokens_left": data.get("tokensLeft"),
        "count": len(result),
        "categories": result,
    }


@app.get("/admin/mark-all-posted")
async def mark_all_posted(token: str = Query(default="")):
    _check_admin(token)
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE products SET telegram_posted = NOW() WHERE telegram_posted IS NULL AND is_active = true"
        )
    count = int(result.split()[-1])
    return {"ok": True, "marked": count, "message": f"{count} bestehende Deals als gepostet markiert — ab jetzt werden nur neue Deals gesendet."}


@app.get("/test-telegram")
async def test_telegram(token: str = Query(default="")):
    _check_admin(token)
    import httpx
    from telegram import TELEGRAM_TOKEN, TELEGRAM_CHANNEL, _build_message
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
        return {"ok": False, "error": "Env-Vars fehlen", "token_set": bool(TELEGRAM_TOKEN), "channel": TELEGRAM_CHANNEL}
    test_deal = {
        "asin":           "B0TEST00001",
        "name":           "snagga.de Telegram-Test — alles funktioniert!",
        "current_price":  19.99,
        "original_price": 39.99,
        "deal_score":     999,
        "tag":            "Allzeittiefpreis",
        "category":       "Elektronik & Foto",
    }
    text = _build_message(test_deal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHANNEL, "text": text, "parse_mode": "MarkdownV2"},
            )
            data = resp.json()
            if data.get("ok"):
                return {"ok": True, "message": "Testnachricht gesendet — schau in deinen Kanal!"}
            return {"ok": False, "telegram_error": data.get("description"), "error_code": data.get("error_code"), "channel": TELEGRAM_CHANNEL}
    except Exception as e:
        return {"ok": False, "exception": str(e)}


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        active  = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active=true")
        backup  = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_backup=true")
        top_p   = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_top_pick=true")
    return {"status": "ok", "active": active or 0, "backup": backup or 0, "top_picks": top_p or 0}
