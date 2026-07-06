"""
Snagga — FastAPI Backend
Endpoints: GET /deals  GET /product/{asin}  GET /categories  POST /refresh
"""
import html
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

load_dotenv()

import alerts
from database import get_pool, init_db
from keepa import enrich_with_keepa
from scraper import (
    fetch_and_update_deals, AFFILIATE_TAG, classify_category, _affiliate_tag_for,
    fetch_and_store_history, PRICE_FRESH_HOURS,
)
from scoring import is_catalog_quality
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
    first_seen:     str = ""
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
        first_seen=str(row["first_seen"]) if row["first_seen"] else str(row["last_updated"] or ""),
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
    # Keine simulierte Fallback-Historie mehr — lieber gar kein Chart als ein
    # erfundener. Ohne echte Daten bleibt price_history leer.
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
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")

# Muss mit den Kategorienamen aus ROOTCAT_MAP / classify_category() in scraper.py
# übereinstimmen — dort werden Produkte diesen exakten Strings zugeordnet.
CATEGORY_SLUGS: dict[str, str] = {
    "auto-motorrad":                  "Auto & Motorrad",
    "baumarkt":                       "Baumarkt",
    "computer-zubehoer":              "Computer & Zubehör",
    "drogerie-koerperpflege":         "Drogerie & Körperpflege",
    "elektro-grossgeraete":           "Elektro-Großgeräte",
    "elektronik-foto":                "Elektronik & Foto",
    "games":                          "Games",
    "kamera-foto":                    "Kamera & Foto",
    "kueche-haushalt-wohnen":         "Küche, Haushalt & Wohnen",
    "musikinstrumente-dj-equipment":  "Musikinstrumente & DJ-Equipment",
    "sport-freizeit":                 "Sport & Freizeit",
}
SLUG_BY_CATEGORY = {v: k for k, v in CATEGORY_SLUGS.items()}


def _arrow_icon(direction: str = "right") -> str:
    """
    Einheitliches Pfeil-Icon für alle Links/Buttons — identisch zum Standard-
    Pfeil im Frontend (CTA "Zum Angebot bei Amazon"). Ersetzt die
    reinen Text-Pfeile (→/←), die uneinheitlich mit dem Rest des Sites wirkten.
    stroke="currentColor" → übernimmt automatisch die Textfarbe des Elternlinks.
    """
    pts    = "12,5 19,12 12,19" if direction == "right" else "12,19 5,12 12,5"
    margin = "margin-left:5px" if direction == "right" else "margin-right:5px"
    return (f'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" '
            f'style="vertical-align:-2px;{margin}">'
            f'<line x1="5" y1="12" x2="19" y2="12"/><polyline points="{pts}"/></svg>')


# Spiegelt TAG_COLORS aus frontend/src/components/DealCard.jsx
_TAG_COLORS = {
    "Allzeittiefpreis":    ("#1a1a1a", "#fff"),
    "Historisch günstig":  ("#2d5a27", "#fff"),
    "Stark gefallen":      ("#8b1a1a", "#fff"),
    "Preis gefallen":      ("#C85E43", "#fff"),
}


def _tag_colors_for(tag: str) -> tuple[str, str] | None:
    """Spiegelt tagStyleFor() aus DealCard.jsx — inkl. Präfix-Match für das
    variable Preishistorie-Urteil "Bester Preis seit X Monaten"."""
    if not tag:
        return None
    if tag.startswith("Bester Preis seit"):
        return ("#1E7A3C", "#fff")
    return _TAG_COLORS.get(tag)

# Kurznamen für die Anzeige — muss mit CAT_LABELS in frontend/src/utils.js
# übereinstimmen, damit SSR-Kacheln/-Seiten dieselbe Bezeichnung zeigen wie die SPA.
_CATEGORY_LABELS = {
    "Drogerie & Körperpflege":         "Körperpflege",
    "Küche, Haushalt & Wohnen":        "Küche & Haushalt",
    "Musikinstrumente & DJ-Equipment": "Musik",
    "Elektro-Großgeräte":              "Grossgeräte",
    "Computer & Zubehör":              "Computer",
    "Elektronik & Foto":               "Elektronik",
    "Auto & Motorrad":                 "Auto",
    "Sport & Freizeit":                "Sport",
    "Kamera & Foto":                   "Kamera",
}

def _cat_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category or "")

# Einleitungstext pro Kategorieseite — gibt Google echten, einzigartigen Inhalt
# (statt nur einem Kachel-Grid = "Thin Content") und erklärt Besuchern den USP.
_CATEGORY_INTROS = {
    "Elektronik & Foto": "Kopfhörer, Fernseher, Tablets, Powerbanks: Elektronik ist besonders anfällig für aufgeblähte Streichpreise. snagga gleicht jeden Deal mit der echten Preishistorie ab, damit du erkennst, ob ein Rabatt wirklich einer ist.",
    "Computer & Zubehör": "Von SSDs und Monitoren bis zu Tastaturen und Mäusen: Diese Computer-Angebote sind gegen die tatsächliche Preisentwicklung geprüft – kein erfundener Streichpreis, sondern echte Bestpreise.",
    "Küche, Haushalt & Wohnen": "Kaffeevollautomaten, Saugroboter, Heißluftfritteusen und Co. werden oft künstlich rabattiert. Hier siehst du zu jedem Produkt den echten Preisverlauf und das Allzeittief.",
    "Games": "Konsolen, Controller und Spiele zum geprüften Bestpreis. Wir gleichen jeden Deal mit der Preishistorie ab, damit du keinen aufgeblähten Streichpreis bezahlst.",
    "Auto & Motorrad": "Dashcams, Pflegeprodukte und Zubehör für Auto und Motorrad – mit geprüfter Preishistorie statt Dauer-Rabatt, der nur so aussieht.",
    "Sport & Freizeit": "Fitnessgeräte, Fahrräder und Outdoor-Ausrüstung: Sport-Deals, deren Rabatt gegen die echte Preisentwicklung geprüft ist.",
    "Drogerie & Körperpflege": "Elektrische Zahnbürsten, Rasierer, Haarpflege und mehr – Drogerie-Angebote, bei denen der Streichpreis mit der tatsächlichen Preishistorie abgeglichen ist.",
    "Baumarkt": "Akkuschrauber, Werkzeug und Hochdruckreiniger von Marken wie Bosch, Makita oder Kärcher – geprüft auf echte Preissenkungen statt Fantasie-Rabatt.",
    "Musikinstrumente & DJ-Equipment": "Gitarren, Keyboards, Audio-Interfaces und DJ-Equipment zum geprüften Bestpreis – der Rabatt wird gegen die tatsächliche Preishistorie kontrolliert.",
    "Kamera & Foto": "Kameras, Objektive, Action-Cams und Stative: Foto-Deals mit echtem Preisverlauf statt erfundenem Streichpreis.",
    "Elektro-Großgeräte": "Waschmaschinen, Kühlschränke, Geschirrspüler und Trockner: Bei grossen Haushaltsgeräten lohnt der Blick auf die echte Preishistorie besonders – snagga zeigt dir, wann der Preis wirklich gefallen ist.",
}

# Repliziert das Kachel-Layout von DealCard.jsx 1:1 (Maße, Farben, Grid-
# Breakpoints) für serverseitig gerenderte Seiten (Kategorie, ähnliche Deals).
_CARD_CSS = """
  .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-top:24px; }
  @media (min-width:768px)  { .grid { grid-template-columns:repeat(3,minmax(0,1fr)); gap:24px; } }
  @media (min-width:1100px) { .grid { grid-template-columns:repeat(4,minmax(0,1fr)); } }
  @media (min-width:1500px) { .grid { grid-template-columns:repeat(5,minmax(0,1fr)); } }
  .card { background:#fff; border:1px solid #EAE6E1; display:flex; flex-direction:column; text-decoration:none; color:#1F1E1D; }
  .card-img { background:#fff; height:240px; display:flex; align-items:center; justify-content:center; padding:24px; position:relative; }
  .card-disc { position:absolute; top:14px; left:14px; background:#C85E43; color:#fff; padding:3px 8px; font-size:11px; font-weight:600; letter-spacing:0.5px; }
  .card-img img { max-width:100%; max-height:190px; object-fit:contain; }
  .card-tag { font-size:10px; font-weight:600; letter-spacing:0.6px; padding:4px 10px; text-transform:uppercase; }
  .card-tag-empty { background:transparent !important; color:transparent !important; }
  .card-body { padding:16px 18px; display:flex; flex-direction:column; flex:1; }
  .card-brand { font-size:10.5px; text-transform:uppercase; letter-spacing:1px; color:#7E7A75; font-weight:500; margin-bottom:7px; }
  .card-name { font-size:14px; font-weight:500; line-height:1.45; color:#1F1E1D; margin-bottom:14px; height:40px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .card-price-row { display:flex; align-items:baseline; gap:8px; margin-bottom:14px; }
  .card-price { font-size:17px; font-weight:700; }
  .card-original { font-size:13px; text-decoration:line-through; color:#7E7A75; }
  .card-footer { border-top:1px solid #EAE6E1; padding-top:11px; font-size:11px; color:#7E7A75; margin-top:auto; display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .card-share { background:none; border:none; cursor:pointer; padding:2px; display:inline-flex; align-items:center; color:#7E7A75; transition:color 0.15s; flex-shrink:0; }
  .card-share:hover { color:#1F1E1D; }
  .card-share.copied { color:#C85E43; }
  .card-share .icon-check { display:none; }
  .card-share.copied .icon-share { display:none; }
  .card-share.copied .icon-check { display:inline-block; }
"""

# Einheitlicher Header für ALLE SSR-Seiten — Logo/Breite 1:1 aus dem
# React-Header (DealsPage.jsx) übernommen, damit sich die SSR-Seiten wie
# Teil der App anfühlen. Rechts-Slot (space-between) für optionale Aktionen
# wie "Zur Startseite" auf Utility-Antwortseiten.
_SITE_HEADER_CSS = """
  header { background:#153D68; height:72px; }
  .site-header-wrap { max-width:1840px; width:98%; margin:0 auto; height:100%; display:flex; align-items:center; justify-content:space-between; }
  .site-header-wrap a.logo { color:#EDE9E3; font-size:28px; font-weight:800; letter-spacing:-0.5px; text-decoration:none; }
  @media (max-width:639px) { .site-header-wrap a.logo { font-size:22px; } }
  .site-header-right a { color:#EDE9E3; font-size:14px; text-decoration:none; padding:8px 16px; border:1px solid rgba(255,255,255,0.25); background:rgba(255,255,255,0.08); transition:background 0.15s; }
  .site-header-right a:hover { background:rgba(255,255,255,0.18); }
  .accent { color:#C85E43; }
"""


def _site_header(right_html: str = "") -> str:
    return ('<header><div class="site-header-wrap">'
            '<a class="logo" href="https://www.snagga.de/">snagga<span class="accent">.de</span></a>'
            f'<div class="site-header-right">{right_html}</div>'
            '</div></header>')


# Rückwärtskompatibler Alias — Aufrufe ohne Rechts-Slot.
_SITE_HEADER_HTML = _site_header()

# Kleines Balken-Chart-Icon (Punkt C) für den "Preisverlauf"-Cue in Listen.
_CHART_ICON = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
               'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
               'style="vertical-align:-2px">'
               '<line x1="4" y1="20" x2="20" y2="20"/>'
               '<rect x="6" y="12" width="3" height="8"/>'
               '<rect x="11" y="7" width="3" height="13"/>'
               '<rect x="16" y="14" width="3" height="6"/>'
               '</svg>')

# Vanilla JS fürs Teilen auf statischen SSR-Kacheln (Kategorie-Seite, "Ähnliche
# Deals") — dort gibt es kein React, daher eigenständige Klick-Logik statt
# der shareOrCopy()-Funktion aus dem Frontend.
_CARD_SHARE_JS = """
<script>
function snaggaShare(e, btn) {
  e.preventDefault(); e.stopPropagation();
  var url = location.origin + '/share/' + btn.dataset.asin;
  var text = btn.dataset.name + ' jetzt für ' + btn.dataset.price + ' auf snagga.de \\uD83D\\uDD25';
  if (navigator.share) { navigator.share({title: btn.dataset.name, text: text, url: url}).catch(function(){}); return; }
  navigator.clipboard.writeText(url).then(function() {
    btn.classList.add('copied');
    setTimeout(function() { btn.classList.remove('copied'); }, 2000);
  }).catch(function(){});
}
</script>
"""


# Interaktives Chart-Fadenkreuz. Wird als <script> auf der /preis-Seite geladen.
# Im React-Modal ist dieselbe Logik als window-Funktion definiert (Frontend), da
# <script>-Tags aus dangerouslySetInnerHTML NICHT ausgeführt werden — die inline
# on*-Handler am SVG rufen in beiden Fällen window.__chartHover/__chartLeave auf.
_CHART_HOVER_JS = """
<script>
window.__chartHover=function(evt,rect){
  var svg=rect.ownerSVGElement; if(!svg)return;
  var pts=svg.__pts||(svg.__pts=JSON.parse(svg.getAttribute('data-pts')||'[]'));
  if(!pts.length)return;
  var pt=svg.createSVGPoint(); pt.x=evt.clientX; pt.y=evt.clientY;
  var ctm=svg.getScreenCTM(); if(!ctm)return;
  var loc=pt.matrixTransform(ctm.inverse());
  var best=pts[0],bd=1e9;
  for(var i=0;i<pts.length;i++){var d=Math.abs(pts[i][0]-loc.x); if(d<bd){bd=d;best=pts[i];}}
  var line=svg.querySelector('.cx-line'),dot=svg.querySelector('.cx-dot'),
      tip=svg.querySelector('.cx-tip'),td=svg.querySelector('.cx-tip-d'),tp=svg.querySelector('.cx-tip-p');
  if(!line||!dot||!tip)return;
  line.setAttribute('x1',best[0]);line.setAttribute('x2',best[0]);line.style.display='';
  dot.setAttribute('cx',best[0]);dot.setAttribute('cy',best[1]);dot.style.display='';
  td.textContent=best[2];tp.textContent=best[3];
  var tw=118,x=best[0]+12; if(x+tw>746)x=best[0]-tw-12; if(x<2)x=2;
  var y=best[1]-48; if(y<2)y=best[1]+14;
  tip.setAttribute('transform','translate('+x+','+y+')');tip.style.display='';
};
window.__chartLeave=function(rect){
  var svg=rect.ownerSVGElement; if(!svg)return;
  ['.cx-line','.cx-dot','.cx-tip'].forEach(function(s){var e=svg.querySelector(s); if(e)e.style.display='none';});
};
</script>
"""


def _deal_card_html(row) -> str:
    """Deal-Karte für Kategorie-Seiten und die 'Ähnliche Deals'-Liste — matcht DealCard.jsx."""
    name     = html.escape((row["name"] or "Deal")[:160])
    image    = html.escape(row["image_url"] or "https://www.snagga.de/favicon.svg")
    current  = row["current_price"]  or 0
    original = row["original_price"] or 0
    price_txt = f"{current:.2f}".replace(".", ",") + " €"
    disc = round((original - current) / original * 100) if original > current else 0
    original_html = f'<span class="card-original">{f"{original:.2f}".replace(".", ",")} €</span>' if original > current else ""
    disc_html     = f'<div class="card-disc">–{disc}%</div>' if disc > 0 else ""

    tag = row["tag"] if "tag" in row.keys() else ""
    tag_colors = _tag_colors_for(tag)
    if tag_colors:
        bg, fg = tag_colors
        tag_html = f'<div class="card-tag" style="background:{bg};color:{fg}">{html.escape(tag)}</div>'
    else:
        tag_html = '<div class="card-tag card-tag-empty">&nbsp;</div>'

    category = html.escape(_cat_label(row["category"])) if "category" in row.keys() and row["category"] else ""

    # Eyebrow-Label: Marke bevorzugt, sonst Bewertung. NIE die Kategorie — die
    # steht schon in der Fusszeile, sonst stuende sie zweimal auf der Kachel.
    # Fehlen Marke UND Bewertung, bleibt der Eyebrow leer (NBSP haelt die Hoehe).
    rating  = row["rating"]  if "rating"  in row.keys() and row["rating"]  else 0
    reviews = row["reviews"] if "reviews" in row.keys() and row["reviews"] else 0
    if reviews >= 1000:
        reviews_txt = f"{reviews / 1000:.1f}".replace(".", ",") + "T"
    elif reviews > 0:
        reviews_txt = str(reviews)
    else:
        reviews_txt = ""
    rating_label = (f"{rating:.1f} ★" + (f" · {reviews_txt}" if reviews_txt else "")) if rating > 0 else ""

    brand = html.escape(row["brand"]) if "brand" in row.keys() and row["brand"] else (rating_label or "&nbsp;")

    return (
        f'<a class="card" href="https://www.snagga.de/deal/{row["asin"]}">'
        f'<div class="card-img">{disc_html}<img src="{image}" alt="{name}" loading="lazy"></div>'
        f'{tag_html}'
        f'<div class="card-body">'
        f'<div class="card-brand">{brand}</div>'
        f'<div class="card-name">{name}</div>'
        f'<div class="card-price-row"><span class="card-price">{price_txt}</span>{original_html}</div>'
        f'<div class="card-footer"><span>{category}</span>'
        f'<button class="card-share" title="Deal teilen" onclick="snaggaShare(event,this)" '
        f'data-asin="{row["asin"]}" data-name="{name}" data-price="{price_txt}">'
        f'<svg class="icon-share" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>'
        f'<line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>'
        f'<svg class="icon-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        f'<polyline points="20 6 9 17 4 12"/></svg>'
        f'</button></div>'
        f'</div></a>'
    )


@app.api_route("/share/{asin}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def share_deal(asin: str):
    """
    Server-gerenderte Preview für geteilte Deal-Links (Telegram, WhatsApp, native
    Share-Sheets). Crawler/Link-Unfurler lesen nur die statischen OG-Tags unten
    und führen kein JS aus; echte Besucher werden per JS sofort zur eigentlichen
    SPA-Seite mit dem Produkt-Modal weitergeleitet. WICHTIG: kein Meta-Refresh
    hier — Telegrams Preview-Crawler folgt dem sonst VOR dem Lesen der OG-Tags
    und zeigt die generische Startseite statt der Produktvorschau.
    """
    target = "https://www.snagga.de/"
    if _ASIN_RE.match(asin):
        target = f"https://www.snagga.de/?asin={asin}"

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
            image = html.escape(row["image_url"] or "https://www.snagga.de/favicon.svg")

            return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>{title}</title>
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


def _not_found_page(message: str) -> HTMLResponse:
    """
    Gebrandete 404-Seite für crawlbare HTML-Routen (/deal, /kategorie) —
    ohne das würden ungültige URLs die rohe {"detail": "..."} JSON-Antwort
    von FastAPIs Standard-Handler anzeigen. Behält echten 404-Status (SEO:
    ein Redirect zur Startseite mit 200 wäre ein "Soft 404" und würde von
    Google negativ bewertet).
    """
    return HTMLResponse(status_code=404, content=f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Seite nicht gefunden | snagga.de</title>
<meta name="robots" content="noindex, follow">
<style>
  body {{ font-family: system-ui, sans-serif; background:#F2EFEA; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:640px; margin:0 auto; padding:60px 20px; text-align:center; }}
  h1 {{ font-size:24px; margin-bottom:8px; }}
  .back {{ display:inline-block; margin-top:20px; background:#C85E43; color:#fff; padding:14px 28px; border-radius:4px; text-decoration:none; font-weight:700; }}
</style>
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<h1>404 — {message}</h1>
<p>Diese Seite gibt es nicht (mehr).</p>
<a class="back" href="https://www.snagga.de/">Zu den aktuellen Deals {_arrow_icon('right')}</a>
</main>
</body>
</html>""")


@app.api_route("/deal/{asin}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def deal_page(asin: str):
    """
    Eigene, serverseitig gerenderte und crawlbare Detailseite pro Deal.
    Anders als /share: KEIN Redirect. Die React-SPA selbst hat nur eine
    einzige URL (Client-Side-Filterung), Google kann darüber also nie
    einzelne Produkte für Long-Tail-Suchen indexieren. Diese Seite schliesst
    die Lücke — eigene URL, eigener Title/Description, JSON-LD Product-Markup.
    """
    if not _ASIN_RE.match(asin):
        return _not_found_page("Ungültige Produkt-ID")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name, brand, image_url, current_price, original_price, tag, category, "
            "rating, reviews, affiliate_url, is_active FROM products WHERE asin=$1",
            asin,
        )
    if not row:
        return _not_found_page("Deal nicht gefunden")

    canonical = f"https://www.snagga.de/deal/{asin}"
    name      = html.escape((row["name"] or "Deal")[:200])
    image     = html.escape(row["image_url"] or "https://www.snagga.de/favicon.svg")
    affiliate = html.escape(row["affiliate_url"] or f"https://www.amazon.de/dp/{asin}")

    # Abgelaufene Deals: Seite bleibt erreichbar (keine toten Links aus Google),
    # aber noindex — verhindert veraltete Preise in den Suchergebnissen. Zeigt
    # stattdessen aktuell aktive Deals, damit Besucher nicht in einer Sackgasse
    # landen und die Seite crawlbaren Linkwert weitergibt (kein Totpunkt).
    if not row["is_active"]:
        pool2 = await get_pool()
        async with pool2.acquire() as conn:
            similar = await conn.fetch(
                "SELECT asin, name, image_url, current_price, original_price, tag, category, brand, rating, reviews "
                "FROM products WHERE is_active=true AND category=$1 AND asin != $2 "
                "ORDER BY deal_score DESC LIMIT 4",
                row["category"], asin,
            )
            if not similar:
                similar = await conn.fetch(
                    "SELECT asin, name, image_url, current_price, original_price, tag, category, brand, rating, reviews "
                    "FROM products WHERE is_active=true ORDER BY deal_score DESC LIMIT 4"
                )

        similar_html = "".join(_deal_card_html(r) for r in similar)
        similar_block = (
            f'<h2>Diese Deals laufen gerade:</h2><div class="grid">{similar_html}</div>'
            if similar else ""
        )

        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Deal nicht mehr verfügbar | snagga.de</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="{canonical}">
<style>
  body {{ font-family: system-ui, sans-serif; background:#F2EFEA; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:1840px; width:98%; margin:0 auto; padding:32px 0; }}
  h1 {{ font-size:22px; }}
  .back {{ display:inline-block; margin-top:8px; color:#153D68; }}
  {_CARD_CSS}
</style>
{_CARD_SHARE_JS}
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<h1>Huch! 👀 Dieser Deal ist schon weg</h1>
<p>„{name}" war ein Snagga-Deal — Deals sind aber flüchtig und laufen ab.</p>
{similar_block}
<p><a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Alle aktuellen Deals ansehen</a></p>
</main>
</body>
</html>""")

    current  = row["current_price"]  or 0
    original = row["original_price"] or 0
    tag      = html.escape(row["tag"] or "")
    category = html.escape(_cat_label(row["category"]) or "")
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

    rating_html = f'<p class="meta">⭐ {rating:.1f} ({reviews} Bewertungen)</p>' if rating > 0 and reviews > 0 else ""

    ld_json: dict = {
        "@context":   "https://schema.org/",
        "@type":      "Product",
        "name":       (row["name"] or "Deal")[:150],
        "image":      [row["image_url"]] if row["image_url"] else [],
        "description": desc,
        "category":   row["category"] or "",
        "offers": {
            "@type":         "Offer",
            "url":           row["affiliate_url"] or affiliate,
            "priceCurrency": "EUR",
            "price":         f"{current:.2f}",
            "availability":  "https://schema.org/InStock",
            "hasMerchantReturnPolicy": {
                "@type":               "MerchantReturnPolicy",
                "applicableCountry":   "DE",
                "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
                "merchantReturnDays":  30,
                "returnMethod":        "https://schema.org/ReturnByMail",
                "returnFees":          "https://schema.org/FreeReturn",
            },
            "shippingDetails": {
                "@type":         "OfferShippingDetails",
                "shippingRate": {
                    "@type":   "MonetaryAmount",
                    "value":   "0",
                    "currency": "EUR",
                },
                "shippingDestination": {
                    "@type":         "DefinedRegion",
                    "addressCountry": "DE",
                },
                "deliveryTime": {
                    "@type": "ShippingDeliveryTime",
                    "handlingTime": {
                        "@type":   "QuantitativeValue",
                        "minValue": 0,
                        "maxValue": 1,
                        "unitCode": "DAY",
                    },
                    "transitTime": {
                        "@type":   "QuantitativeValue",
                        "minValue": 1,
                        "maxValue": 3,
                        "unitCode": "DAY",
                    },
                },
            },
        },
    }
    if row["brand"]:
        ld_json["brand"] = {"@type": "Brand", "name": row["brand"]}
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
  body {{ font-family: system-ui, sans-serif; background:#FAF8F5; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  .wrap {{ max-width:1840px; width:98%; margin:32px auto; background:#fff; display:grid; grid-template-columns:1fr 1.15fr; box-shadow:0 4px 24px rgba(0,0,0,0.06); position:relative; }}
  @media (max-width:760px) {{ .wrap {{ grid-template-columns:1fr; margin:0; }} }}
  .page-share {{ position:absolute; top:20px; right:20px; z-index:5; display:flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:50%; background:#fff; border:none; cursor:pointer; color:#7E7A75; box-shadow:0 1px 4px rgba(0,0,0,0.1); transition:background 0.15s, color 0.15s; }}
  .page-share:hover {{ background:#FAF9F7; color:#1F1E1D; }}
  .page-share.copied {{ color:#C85E43; }}
  .page-share .icon-check {{ display:none; }}
  .page-share.copied .icon-share {{ display:none; }}
  .page-share.copied .icon-check {{ display:inline-block; }}
  .gallery {{ background:#fff; padding:48px; display:flex; align-items:center; justify-content:center; border-right:1px solid #EAE6E1; }}
  @media (max-width:760px) {{ .gallery {{ border-right:none; border-bottom:1px solid #EAE6E1; padding:32px; }} }}
  .gallery img {{ max-width:100%; max-height:460px; object-fit:contain; }}
  .details {{ padding:56px 52px; }}
  @media (max-width:760px) {{ .details {{ padding:32px 24px; }} }}
  .brand {{ font-size:11px; text-transform:uppercase; letter-spacing:1.5px; color:#7E7A75; font-weight:600; margin-bottom:10px; }}
  .tag {{ display:inline-block; background:#C85E43; color:#fff; font-size:13px; font-weight:700; padding:4px 10px; margin-bottom:12px; }}
  h1 {{ font-size:31px; font-weight:700; line-height:1.35; margin:0 0 24px; }}
  .price-row {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:16px; }}
  .price {{ font-size:38px; font-weight:700; }}
  .original {{ font-size:16px; text-decoration:line-through; color:#7E7A75; font-weight:400; }}
  .disc {{ background:#C85E43; color:#fff; padding:3px 9px; font-size:12px; font-weight:600; }}
  .meta {{ font-size:13px; color:#7E7A75; margin:0 0 8px; }}
  .cta {{ display:flex; align-items:center; justify-content:center; gap:10px; background:#C85E43; color:#fff; padding:16px 28px; font-size:14px; font-weight:600; text-decoration:none; margin-top:20px; }}
  .back {{ display:block; margin-top:16px; color:#153D68; font-size:14px; text-decoration:none; }}
  .affiliate-note {{ font-size:12px; color:#7E7A75; line-height:1.5; margin:18px 0 0; }}
</style>
{_CARD_SHARE_JS}
</head>
<body>
{_SITE_HEADER_HTML}
<div class="wrap">
  <button class="page-share" title="Deal teilen" onclick="snaggaShare(event,this)" data-asin="{asin}" data-name="{name}" data-price="{price_txt}">
    <svg class="icon-share" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
    </svg>
    <svg class="icon-check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </button>
  <div class="gallery"><img src="{image}" alt="{name}"></div>
  <div class="details">
    <div class="brand">{category}</div>
    {f'<div class="tag">{tag}</div>' if tag else ''}
    <h1>{name}</h1>
    <div class="price-row">
      <span class="price">{price_txt}</span>
      {f'<span class="original">{original_txt}</span>' if disc > 0 else ''}
      {f'<span class="disc">-{disc}%</span>' if disc > 0 else ''}
    </div>
    {rating_html}
    <p class="meta">Kategorie: {category}</p>
    <a class="cta" href="{affiliate}" rel="nofollow sponsored noopener" target="_blank">Zum Angebot bei Amazon {_arrow_icon('right')}</a>
    <p class="affiliate-note">* Affiliate-Hinweis: Als Amazon-Partner verdienen wir an qualifizierten Käufen — für dich entstehen keine Mehrkosten. Der angezeigte Preis kann abweichen; massgeblich ist der Preis bei Amazon zum Kaufzeitpunkt.</p>
    <a class="back" href="https://www.snagga.de/preis/{asin}">📈 Preisverlauf & Preis-Check ansehen {_arrow_icon('right')}</a>
    {f'<a class="back" href="https://www.snagga.de/kategorie/{SLUG_BY_CATEGORY[row["category"]]}">Alle {category}-Deals ansehen {_arrow_icon("right")}</a>' if row["category"] in SLUG_BY_CATEGORY else ''}
    <a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Alle Deals ansehen</a>
  </div>
</div>
</body>
</html>""")


@app.api_route("/feed.xml", methods=["GET", "HEAD"])
async def rss_feed():
    """
    RSS 2.0-Feed der aktuell aktiven Deals — erreicht Feed-Reader und
    Deal-Aggregator-Bots automatisch, ohne dass jemand manuell posten muss.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, name, current_price, original_price, tag, category, "
            "first_seen, last_updated FROM products WHERE is_active=true "
            "ORDER BY first_seen DESC NULLS LAST, last_updated DESC LIMIT 50"
        )

    def rfc822(dt) -> str:
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000") if dt else ""

    items = []
    for r in rows:
        current  = r["current_price"]  or 0
        original = r["original_price"] or 0
        price_txt = f"{current:.2f}".replace(".", ",") + " €"
        disc = round((original - current) / original * 100) if original > current else 0
        title = html.escape(
            f"{r['name'] or 'Deal'} für {price_txt}" + (f" (-{disc}%)" if disc > 0 else "")
        )
        link = f"https://www.snagga.de/deal/{r['asin']}"
        desc = html.escape(
            (r["tag"] or r["category"] or "Deal") + f" — {price_txt} auf snagga.de"
        )
        pubdate = rfc822(r["first_seen"] or r["last_updated"])
        items.append(
            "<item>"
            f"<title>{title}</title>"
            f"<link>{link}</link>"
            f'<guid isPermaLink="true">{link}</guid>'
            f"<description>{desc}</description>"
            + (f"<pubDate>{pubdate}</pubDate>" if pubdate else "")
            + "</item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>snagga — Aktuelle Amazon-Deals</title>"
        "<link>https://www.snagga.de/</link>"
        "<description>Täglich handverlesene Amazon-Bestpreise mit geprüfter Preishistorie</description>"
        "<language>de-de</language>"
        + "".join(items) +
        "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")


@app.api_route("/kategorie/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def category_page(slug: str):
    """
    Dauerhafte, serverseitig gerenderte Kategorie-Seite. Anders als einzelne
    Deal-Seiten (/deal/{asin}) läuft diese URL nie ab — Deals kommen und gehen,
    aber die Kategorie-Seite bleibt bestehen und kann über Zeit Google-Vertrauen
    aufbauen. Wichtig, weil einzelne Deals oft schon vor der Erstindexierung
    wieder ablaufen (Rotation stündlich) und daher als SEO-Basis ungeeignet sind.
    """
    if not _SLUG_RE.match(slug) or slug not in CATEGORY_SLUGS:
        return _not_found_page("Kategorie nicht gefunden")

    category  = CATEGORY_SLUGS[slug]
    canonical = f"https://www.snagga.de/kategorie/{slug}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, name, image_url, current_price, original_price, tag, category, brand, rating, reviews "
            "FROM products WHERE is_active=true AND category=$1 "
            "ORDER BY deal_score DESC LIMIT 60",
            category,
        )

    count = len(rows)
    cat_esc = html.escape(category)

    if count:
        title = f"{cat_esc} Angebote — {count} aktuelle Amazon-Deals | snagga.de"
        desc  = html.escape(
            f"{count} aktuelle {category}-Deals mit geprüfter Preishistorie — "
            f"täglich aktualisiert auf snagga.de."
        )
        robots = "index, follow"
        body_extra = f'<div class="grid">{"".join(_deal_card_html(r) for r in rows)}</div>'
        ld_json = {
            "@context": "https://schema.org/",
            "@type":    "ItemList",
            "itemListElement": [
                {
                    "@type":    "ListItem",
                    "position": i + 1,
                    "url":      f"https://www.snagga.de/deal/{r['asin']}",
                    "name":     r["name"] or "Deal",
                }
                for i, r in enumerate(rows)
            ],
        }
        ld_script = f'<script type="application/ld+json">{json.dumps(ld_json, ensure_ascii=False)}</script>'
    else:
        title = f"{cat_esc} Angebote | snagga.de"
        desc  = html.escape(f"Aktuell keine {category}-Deals — schau bald wieder vorbei.")
        robots = "noindex, follow"
        body_extra = '<p>Gerade läuft in dieser Kategorie kein Deal. Schau bald wieder vorbei!</p>'
        ld_script = ""

    intro_html = (f'<p class="cat-intro">{html.escape(_CATEGORY_INTROS[category])}</p>'
                  if category in _CATEGORY_INTROS else "")

    other_cats = "".join(
        f'<a href="https://www.snagga.de/kategorie/{s}">{html.escape(n)}</a>'
        for s, n in CATEGORY_SLUGS.items() if s != slug
    )

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
{ld_script}
<style>
  body {{ font-family: system-ui, sans-serif; background:#FAF8F5; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:1840px; width:98%; margin:0 auto; padding:32px 0; }}
  h1 {{ font-size:26px; margin-bottom:4px; }}
  .cat-intro {{ font-size:15px; line-height:1.6; color:#3a3a3a; margin:12px 0 28px; }}
  {_CARD_CSS}
  .catnav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:40px; }}
  .catnav a {{ font-size:13px; background:#fff; border-radius:20px; padding:6px 14px; text-decoration:none; color:#153D68; }}
  .back {{ display:inline-block; margin-top:20px; color:#153D68; }}
</style>
{_CARD_SHARE_JS}
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<h1>{cat_esc} Angebote</h1>
{intro_html}
<p>{desc}</p>
{body_extra}
<nav class="catnav">{other_cats}</nav>
<p><a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Alle Deals ansehen</a></p>
</main>
</body>
</html>""")


def _price_verdict(current: float, avg90: float, atl: float) -> tuple[str, str, str]:
    """
    Urteil "Guter Preis?" — Ja / Warten / Nein, basierend auf aktuellem Preis
    vs. 90-Tage-Durchschnitt und Allzeittief. Spiegelt chartStatus() im Frontend,
    gibt aber eine klare Kaufempfehlung als (Label, Farbe, Begründung) zurück.
    """
    if not current or current <= 0:
        return ("Unbekannt", "#7E7A75", "Für dieses Produkt liegt gerade kein aktueller Preis vor.")
    if atl and current <= atl * 1.02:
        return ("Ja", "#1E7A3C", "Günstigster Preis seit Messbeginn — besser wird es selten.")
    if avg90 and current <= avg90 * 0.85:
        return ("Ja", "#1E7A3C", "Selten so günstig — deutlich unter dem 90-Tage-Durchschnitt.")
    if avg90 and current <= avg90 * 0.95:
        return ("Ja", "#2d5a27", "Guter Preis — spürbar unter dem 90-Tage-Durchschnitt.")
    if avg90 and current <= avg90 * 1.02:
        return ("Eher warten", "#C85E43", "Nur knapp unter dem Durchschnitt — ein besserer Preis ist wahrscheinlich.")
    return ("Nein", "#8b1a1a", "Aktuell kein guter Preis — er liegt über dem 90-Tage-Durchschnitt.")


def _parse_ts(raw) -> Optional[datetime]:
    """TEXT-Zeitstempel (asyncpg-str oder ISO) robust nach datetime — sonst None."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip().replace("T", " ")
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _price_chart_svg(points: list, avg90: float, atl: float,
                     current: float = 0, days: int | None = None) -> str:
    """
    Inline-SVG-Preisverlauf als TREPPENKURVE mit echter Zeitachse (SSR, kein JS).
    points: chronologische Liste (Preis, Zeitstempel). Der Preis hält konstant bis
    zur nächsten Änderung (step-after) — so wie Keepa, statt schräger Interpolation.
    current: aktueller Preis — wird als letzter Punkt angehängt, damit die Linie
             immer beim heutigen Preis endet (die Keepa-Serie kann nachlaufen).
    days:    zeigt nur die letzten N Tage (Default-Ansicht); None = ganze History.
    """
    parsed = [(float(p), _parse_ts(ts)) for p, ts in points if p and float(p) > 0]

    # Aktuellen Preis als Schlusspunkt anhängen, damit die Linie beim heutigen
    # Preis endet (behebt "Linie hängt in der Vergangenheit fest").
    if current and current > 0:
        now_dt = datetime.utcnow()
        last_p, last_t = parsed[-1] if parsed else (None, None)
        if last_p is None or abs(last_p - current) > 0.005 or (last_t and last_t < now_dt - timedelta(days=1)):
            parsed.append((float(current), now_dt))

    # Optional auf die letzten `days` Tage fenstern (Default). Bleiben dabei <2
    # Punkte übrig (z.B. seltene Preisänderungen), ganze Serie zeigen.
    if days and parsed:
        cutoff   = datetime.utcnow() - timedelta(days=days)
        windowed = [x for x in parsed if x[1] and x[1] >= cutoff]
        if len(windowed) >= 2:
            parsed = windowed

    if len(parsed) < 2:
        return ""
    prices = [p for p, _ in parsed]
    times  = [t for _, t in parsed]
    have_time = all(t is not None for t in times) and times[0] != times[-1]

    W, H = 760, 264
    PAD_L, PAD_R, PAD_T, PAD_B = 52, 14, 16, 42
    chart_w, chart_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    minv, maxv = min(prices), max(prices)
    pad = (maxv - minv) * 0.08 or maxv * 0.05
    ymin, ymax = max(0, minv - pad), maxv + pad
    rng = (ymax - ymin) or 1
    n = len(prices)

    if have_time:
        t0, t1 = times[0].timestamp(), times[-1].timestamp()
        span = (t1 - t0) or 1
        xs = [PAD_L + ((t.timestamp() - t0) / span) * chart_w for t in times]
    else:
        xs = [PAD_L + (i / (n - 1)) * chart_w for i in range(n)]

    def to_y(p: float) -> float: return PAD_T + chart_h - ((p - ymin) / rng) * chart_h
    def fmt(v: float) -> str: return f"{v:.0f} €"

    ys = [to_y(p) for p in prices]
    # Treppe (step-after): erst horizontal auf altem Preis bis zum neuen Zeitpunkt,
    # dann senkrechter Sprung auf den neuen Preis.
    seg = [f"M{xs[0]:.1f},{ys[0]:.1f}"]
    for i in range(1, n):
        seg.append(f"L{xs[i]:.1f},{ys[i-1]:.1f}")
        seg.append(f"L{xs[i]:.1f},{ys[i]:.1f}")
    path_d = " ".join(seg)
    fill_d = f"{path_d} L{xs[-1]:.1f},{PAD_T + chart_h:.1f} L{PAD_L:.1f},{PAD_T + chart_h:.1f} Z"
    cx, cy = xs[-1], ys[-1]

    avg_line = ""
    if avg90 and ymin <= avg90 <= ymax:
        ay = to_y(avg90)
        avg_line = (
            f'<line x1="{PAD_L}" y1="{ay:.1f}" x2="{W - PAD_R}" y2="{ay:.1f}" stroke="#7E7A75" stroke-width="1.2" stroke-dasharray="4,3"/>'
            f'<text x="{W - PAD_R}" y="{ay - 4:.1f}" text-anchor="end" font-size="11" fill="#7E7A75">Ø 90 Tage {fmt(avg90)}</text>'
        )
    atl_line = ""
    if atl and ymin <= atl <= ymax:
        ty = to_y(atl)
        atl_line = (
            f'<line x1="{PAD_L}" y1="{ty:.1f}" x2="{W - PAD_R}" y2="{ty:.1f}" stroke="#1E7A3C" stroke-width="1" stroke-dasharray="2,3"/>'
            f'<text x="{W - PAD_R}" y="{ty + 12:.1f}" text-anchor="end" font-size="11" fill="#1E7A3C">Tief {fmt(atl)}</text>'
        )

    # X-Achse: echte Datums-Labels + feine vertikale Gitterlinien an 5 Stützstellen
    xaxis, vgrid = "", ""
    if have_time:
        for k in range(5):
            frac = k / 4
            x = PAD_L + frac * chart_w
            tdt = datetime.fromtimestamp(t0 + frac * span)
            anchor = "start" if k == 0 else ("end" if k == 4 else "middle")
            xaxis += (f'<text x="{x:.1f}" y="{H - 8}" text-anchor="{anchor}" '
                      f'font-size="11" fill="#7E7A75">{tdt.strftime("%d.%m.%y")}</text>')
            if 0 < k < 4:
                vgrid += f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{PAD_T + chart_h}" stroke="#F0ECE7"/>'
    else:
        xaxis = (f'<text x="{PAD_L}" y="{H - 8}" text-anchor="start" font-size="11" fill="#7E7A75">früher</text>'
                 f'<text x="{W - PAD_R}" y="{H - 8}" text-anchor="end" font-size="11" fill="#7E7A75">heute</text>')

    ymid = (ymax + ymin) / 2

    # Interaktiver Hover: Datenpunkte als JSON am SVG. Ein globales __chartHover
    # (SSR per <script>, Modal per window-Funktion) liest sie und bewegt Fadenkreuz,
    # Punkt und Tooltip. Inline on*-Handler laufen auch, wenn das SVG per innerHTML/
    # dangerouslySetInnerHTML eingefügt wird (<script>-Tags dagegen NICHT).
    pts_data = json.dumps([[round(xs[i], 1), round(ys[i], 1),
                            (times[i].strftime("%d.%m.%y") if times[i] else ""),
                            (f"{prices[i]:.2f}".replace(".", ",") + " €")] for i in range(n)])
    x_right = W - PAD_R

    return f"""<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Preisverlauf" data-pts='{html.escape(pts_data, quote=True)}' style="display:block;overflow:visible">
  <defs><linearGradient id="pcgrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#C85E43" stop-opacity="0.15"/><stop offset="100%" stop-color="#C85E43" stop-opacity="0"/>
  </linearGradient></defs>
  {vgrid}
  <line x1="{PAD_L}" y1="{PAD_T}" x2="{x_right}" y2="{PAD_T}" stroke="#EAE6E1"/>
  <line x1="{PAD_L}" y1="{PAD_T + chart_h / 2:.1f}" x2="{x_right}" y2="{PAD_T + chart_h / 2:.1f}" stroke="#EAE6E1"/>
  <line x1="{PAD_L}" y1="{PAD_T + chart_h}" x2="{x_right}" y2="{PAD_T + chart_h}" stroke="#EAE6E1"/>
  <text x="{PAD_L - 6}" y="{PAD_T + 4}" text-anchor="end" font-size="11" fill="#1F1E1D">{fmt(ymax)}</text>
  <text x="{PAD_L - 6}" y="{PAD_T + chart_h / 2 + 4:.1f}" text-anchor="end" font-size="11" fill="#1F1E1D">{fmt(ymid)}</text>
  <text x="{PAD_L - 6}" y="{PAD_T + chart_h + 4}" text-anchor="end" font-size="11" fill="#1F1E1D">{fmt(ymin)}</text>
  {avg_line}{atl_line}
  <path d="{fill_d}" fill="url(#pcgrad)"/>
  <path d="{path_d}" fill="none" stroke="#C85E43" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#C85E43"/>
  {xaxis}
  <line class="cx-line" x1="0" y1="{PAD_T}" x2="0" y2="{PAD_T + chart_h}" stroke="#7E7A75" stroke-width="1" stroke-dasharray="3,3" style="display:none;pointer-events:none"/>
  <circle class="cx-dot" r="4.5" fill="#153D68" stroke="#fff" stroke-width="1.5" style="display:none;pointer-events:none"/>
  <g class="cx-tip" style="display:none;pointer-events:none">
    <rect rx="3" fill="#1F1E1D" opacity="0.92" width="118" height="40"/>
    <text class="cx-tip-d" x="9" y="16" font-size="11" fill="#D8D3CC"></text>
    <text class="cx-tip-p" x="9" y="32" font-size="13" font-weight="700" fill="#fff"></text>
  </g>
  <rect class="cx-hit" x="{PAD_L}" y="{PAD_T}" width="{chart_w}" height="{chart_h}" fill="transparent" style="cursor:crosshair" onmousemove="window.__chartHover&amp;&amp;window.__chartHover(event,this)" onmouseleave="window.__chartLeave&amp;&amp;window.__chartLeave(this)"/>
</svg>"""


def _compute_detail(row, hist_rows) -> dict:
    """
    Gemeinsame Berechnung der Produktdetails: Preise, geklemmtes Allzeittief,
    Kauf-Urteil, Preisverlauf-Chart (SVG) und Wunschpreis-Vorschlag. EINE Quelle
    für die SSR-Preisseite (/preis) UND das JSON fürs Modal (/produkt) — so
    zeigen beide garantiert dieselben Zahlen, dasselbe Urteil und denselben Chart.
    """
    points  = [(h["price"], h["timestamp"]) for h in reversed(hist_rows) if h["price"] and h["price"] > 0]
    current = row["current_price"] or 0
    avg90   = row["avg90_price"] or row["avg_price"] or 0
    avg180  = row["avg180_price"] or 0
    atl     = row["all_time_low"] or 0
    # ATL konsistent zum angezeigten Chart: das echte Tief der gespeicherten
    # Historie einbeziehen. Sonst behauptet das Urteil "günstigster Preis seit
    # Messbeginn", obwohl der Chart sichtbar einen tieferen Punkt zeigt.
    hist_min = min((p for p, _ in points), default=0)
    if hist_min and (not atl or hist_min < atl):
        atl = hist_min
    # Anzeige-Sicherung: Ein Allzeittief kann logisch nie über dem aktuellen Preis liegen.
    if atl and current and atl > current:
        atl = current
    verdict, vcolor, vreason = _price_verdict(current, avg90, atl)
    # Chart nur mit verifizierter Keepa-Historie — nie erfundene Kurven zeigen.
    # Drei Zeitfenster für den 90/365/Gesamt-Umschalter auf der Preisseite;
    # chart_svg (=365 Tage) und chart_svg_full bleiben unverändert, damit das
    # bestehende Modal-Chart-Umschalten (React) unangetastet weiterläuft.
    if row["has_real_history"]:
        chart_svg_90   = _price_chart_svg(points, avg90, atl, current=current, days=90)
        chart_svg      = _price_chart_svg(points, avg90, atl, current=current, days=365)
        chart_svg_full = _price_chart_svg(points, avg90, atl, current=current)
    else:
        chart_svg_90 = chart_svg = chart_svg_full = ""
    # Umschalter nur zeigen, wenn es History älter als 365 Tage gibt.
    has_more = False
    if row["has_real_history"] and points:
        oldest = _parse_ts(points[0][1])
        has_more = bool(oldest and oldest < datetime.utcnow() - timedelta(days=365)
                        and chart_svg_full and chart_svg_full != chart_svg)
    if current and current > 0:
        suggested = round(current * 0.9, 2)
    elif atl and atl > 0:
        suggested = round(atl, 2)
    else:
        suggested = ""
    return {
        "current": current, "avg90": avg90, "avg180": avg180, "atl": atl,
        "verdict": verdict, "vcolor": vcolor, "vreason": vreason,
        "chart_svg_90": chart_svg_90, "chart_svg": chart_svg, "chart_svg_full": chart_svg_full,
        "has_more_history": has_more, "suggested": suggested,
        "is_active": bool(row["is_active"]) if "is_active" in row.keys() else True,
    }


@app.get("/produkt/{asin}")
async def api_product_detail(asin: str):
    """
    JSON-Detaildaten fürs Produkt-Modal: Urteil, Preis-Eckdaten, Chart-SVG und
    Wunschpreis-Vorschlag — dieselbe Quelle wie die SSR-Seite /preis/{asin}, damit
    das Modal exakt dasselbe zeigt. Der Chart kommt als fertiges SVG (1:1 identisch
    zur Preisseite); das Frontend bettet ihn direkt ein.
    """
    if not re.match(r"^[A-Z0-9]{10}$", asin):
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT asin, name, avg_price, avg90_price, avg180_price, all_time_low, "
            "current_price, is_active, has_real_history FROM products WHERE asin=$1",
            asin,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        hist = await conn.fetch(
            "SELECT price, timestamp FROM price_history WHERE asin=$1 ORDER BY id DESC LIMIT 2000",
            asin,
        )
    d = _compute_detail(row, hist)
    return {
        "asin":             asin,
        "verdict":          {"label": d["verdict"], "color": d["vcolor"], "reason": d["vreason"]},
        "current_price":    d["current"],
        "atl":              d["atl"],
        "avg90":            d["avg90"],
        "avg180":           d["avg180"],
        "has_real_history": bool(row["has_real_history"]),
        "chart_svg":        d["chart_svg"],
        "chart_svg_full":   d["chart_svg_full"],
        "has_more_history": d["has_more_history"],
        "suggested_target": d["suggested"],
        "is_active":        bool(row["is_active"]),
    }


# ---------------------------------------------------------------------------
# Preis-Check — Suchbox-Backend (Kern der Utility-Positionierung):
# Amazon-Link/ASIN/Produktname rein → Urteil auf der /preis/{asin}-Seite.
# Unbekannte ASINs werden live via Keepa geholt (1 Token) und dauerhaft in
# die products-Tabelle aufgenommen → jede Nutzer-Anfrage vergrößert den
# indexierbaren /preis/-Seitenbestand.
# ---------------------------------------------------------------------------

_ASIN_URL_RE  = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})", re.IGNORECASE)
_ASIN_BARE_RE = re.compile(r"^\s*(B[0-9A-Z]{9})\s*$", re.IGNORECASE)
_SHORTLINK_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:amzn\.to|amzn\.eu|a\.co)/", re.IGNORECASE)

# Zubehör-Wörter für die Suchtreffer-Sortierung: Kernprodukte (z.B. das Handy
# selbst) sollen vor Zubehör (Hülle, Ladekabel, ...) stehen — sonst gewinnt oft
# die Hülle, weil sie eher ein Deal-Signal (aktiv/Score) hat als das Gerät.
_ACCESSORY_RE = re.compile(
    r"h[üu]lle|case|cover|schutzfolie|panzerglas|folie|tasche|st[äa]nder|"
    r"halterung|ladekabel|ladeger[äa]t|netzteil|adapter|armband|ersatzteil|"
    r"schutzh[üu]lle|geh[äa]use",
    re.IGNORECASE,
)

# Schutz des Keepa-Budgets: Live-Lookups (= unbekannte ASINs) pro IP und global
# gedeckelt. DB-Treffer und Namenssuchen kosten nichts und sind nicht limitiert.
_pc_ip_hits: dict[str, list[float]] = {}
_pc_daily = {"day": "", "count": 0}
PC_IP_LOOKUPS_PER_HOUR    = 8
PC_GLOBAL_LOOKUPS_PER_DAY = 400   # ~1.4% des Keepa-Tagesbudgets (28'800)


def _pc_rate_ok(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _pc_ip_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= PC_IP_LOOKUPS_PER_HOUR:
        _pc_ip_hits[ip] = hits
        return False
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if _pc_daily["day"] != today:
        _pc_daily["day"], _pc_daily["count"] = today, 0
    if _pc_daily["count"] >= PC_GLOBAL_LOOKUPS_PER_DAY:
        return False
    if len(_pc_ip_hits) > 5000:  # Speicher-Hygiene (Render Free, 1 Instanz)
        _pc_ip_hits.clear()
    hits.append(now)
    _pc_ip_hits[ip] = hits
    _pc_daily["count"] += 1
    return True


def _extract_asin(q: str) -> str:
    m = _ASIN_BARE_RE.match(q)
    if m:
        return m.group(1).upper()
    m = _ASIN_URL_RE.search(q)
    if m:
        return m.group(1).upper()
    return ""


async def _resolve_shortlink(url: str) -> str:
    """Löst amzn.to/amzn.eu/a.co-Kurzlinks per Redirect-Verfolgung auf (kein Keepa-Token)."""
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
            resp = await c.head(url if url.startswith("http") else f"https://{url}")
            return str(resp.url)
    except Exception:
        return ""


def _pc_shell(title_txt: str, body_html: str, status: int = 200) -> HTMLResponse:
    """Gebrandete Hülle für Preis-Check-Antwortseiten (noindex — reine Utility-Antworten)."""
    return HTMLResponse(status_code=status, content=f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title_txt)} | snagga.de</title>
<meta name="robots" content="noindex, follow">
<style>
  body {{ font-family: system-ui, sans-serif; background:#F2EFEA; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:1840px; width:98%; margin:0 auto; padding:32px 0 48px; }}
  h1 {{ font-size:24px; margin-bottom:16px; }}
  p  {{ line-height:1.6; color:#3a3a3a; }}
  .results a {{ display:flex; gap:16px; align-items:center; background:#fff; border:1px solid #EAE6E1;
               padding:14px 18px; margin-bottom:10px; text-decoration:none; color:#1F1E1D; }}
  .results a:hover {{ border-color:#153D68; }}
  .results img {{ width:56px; height:56px; object-fit:contain; flex-shrink:0; }}
  .results .r-main {{ min-width:0; flex:1 1 auto; overflow:hidden; }}
  .results .r-name {{ font-size:15px; font-weight:600; line-height:1.4; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .results .r-tag {{ display:inline-block; font-size:12px; color:#1E7A3C; margin-top:4px; }}
  .results .r-side {{ display:flex; flex-direction:column; align-items:flex-end; gap:2px; margin-left:16px; flex-shrink:0; text-align:right; min-width:120px; }}
  .results .r-price {{ font-size:15px; font-weight:700; white-space:nowrap; }}
  .results .r-cue {{ display:inline-flex; align-items:center; gap:5px; font-size:12px; color:#153D68; }}
  .hint {{ background:#fff; border:1px solid #EAE6E1; padding:14px 18px; font-size:14px; margin-top:18px; max-width:820px; }}
</style>
</head>
<body>
{_site_header('<a href="https://www.snagga.de/">Zur Startseite</a>')}
<main>
{body_html}
</main>
</body>
</html>""")


@app.get("/preis-check")
async def preis_check(request: Request, q: str = Query(default="")):
    q = (q or "").strip()
    if not q:
        return RedirectResponse("https://www.snagga.de/", status_code=302)

    asin = _extract_asin(q)

    # amzn.to/amzn.eu-Kurzlink → Redirect auflösen (kostenlos), dann erneut suchen
    if not asin and _SHORTLINK_RE.match(q):
        resolved = await _resolve_shortlink(q)
        asin = _extract_asin(resolved)

    pool = await get_pool()

    if asin:
        async with pool.acquire() as conn:
            known = await conn.fetchval("SELECT 1 FROM products WHERE asin=$1", asin)
        if known:
            return RedirectResponse(f"https://www.snagga.de/preis/{asin}", status_code=302)

        # Unbekanntes Produkt → Live-Lookup (1 Keepa-Token), Budget-geschützt
        ip = (request.headers.get("x-forwarded-for")
              or (request.client.host if request.client else "?")).split(",")[0].strip()
        if not _pc_rate_ok(ip):
            return _pc_shell("Zu viele Anfragen",
                             "<h1>Kurz durchatmen 😅</h1>"
                             "<p>Du hast gerade viele neue Produkte geprüft. Jede Prüfung fragt "
                             "live die Preisdatenbank ab — bitte versuch es in einer Stunde noch einmal.</p>",
                             status=429)

        data = await enrich_with_keepa([asin], domain=3)
        kd = data.get(asin)
        if not kd or not kd.get("current_price"):
            return _pc_shell("Produkt nicht gefunden",
                             "<h1>Kein Preis gefunden</h1>"
                             "<p>Unter diesem Amazon-Link konnten wir kein Produkt mit Preisdaten "
                             "finden — möglicherweise ist es nicht (mehr) auf amazon.de gelistet.</p>",
                             status=404)

        # Kategorie aus rootCat + Titel bestimmen (statt hart "Sonstiges"). Fällt
        # die Klassifikation aus (Junk-rootCat/kein Keyword-Match), bleibt es
        # "Sonstiges" — die Seite existiert trotzdem, nur ohne Kategorie-Einordnung.
        category = classify_category(kd["title"] or "", kd.get("root_cat") or 0) or "Sonstiges"
        # Affiliate-Tag passend zur Kategorie (getaggte Kategorie → eigener
        # Tracking-Tag, sonst snagga-Standardtag).
        aff_tag = _affiliate_tag_for(category)

        # Dauerhaft aufnehmen: is_active=false (kein Deal), aber /preis/-Seite
        # existiert ab jetzt für immer und wandert in die Sitemap.
        now  = datetime.utcnow()
        hist = kd.get("history") or []
        hist_prices    = [pr for pr, _ in hist if pr and pr > 0]
        atl_candidates = [v for v in (kd["all_time_low"], kd["current_price"],
                                      min(hist_prices) if hist_prices else None) if v and v > 0]
        atl = min(atl_candidates) if atl_candidates else kd["current_price"]

        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO products
                  (asin, name, brand, image_url, category,
                   current_price, original_price, all_time_low, avg_price,
                   avg90_price, avg180_price, deal_score, rating, reviews, prime,
                   last_updated, last_checked, affiliate_url,
                   is_active, is_backup, is_top_pick, is_fba,
                   sales_rank, tag, score_breakdown, first_seen)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                        $16,$17,$18,false,false,false,$19,$20,'','',$16)
                ON CONFLICT (asin) DO NOTHING
            """,
                asin, (kd["title"] or "Produkt")[:200], kd.get("brand") or "",
                kd["image_url"], category,
                kd["current_price"], kd["original_price"], atl, kd["avg_price"],
                kd["avg90_price"] or 0.0, kd["avg180_price"] or 0.0,
                0, kd["rating"], kd["reviews"], True,
                now, now, f"https://www.amazon.de/dp/{asin}?tag={aff_tag}",
                kd["is_fba"], kd["sales_rank"] or 0,
            )
            if hist:
                await conn.execute("DELETE FROM price_history WHERE asin=$1", asin)
                await conn.executemany(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    [(asin, pr, ts) for pr, ts in hist[-2000:]],
                )
                await conn.execute(
                    "UPDATE products SET has_real_history=true WHERE asin=$1", asin
                )
        return RedirectResponse(f"https://www.snagga.de/preis/{asin}", status_code=302)

    # Kein Link/keine ASIN → Namenssuche im eigenen (bereinigten) Bestand.
    # Tokenized: jedes Wort muss im Namen ODER in der Marke vorkommen — "Sandisk USB"
    # findet auch "SANDISK Phone Drive mit USB Type-C" (die alte %ganzer-string%-
    # Suche fand nichts, weil die Wörter im Titel nicht direkt aufeinander folgen).
    tokens = [t for t in re.split(r"\s+", q[:80].strip()) if t][:6]
    if tokens:
        conds = " AND ".join(
            f"(name ILIKE '%' || ${i+1} || '%' OR brand ILIKE '%' || ${i+1} || '%')"
            for i in range(len(tokens))
        )
        # Grosszügiger Kandidaten-Pool (60), damit nach dem Zubehör-Nachrücken
        # (unten) noch genug "echte" Produkte für die Top-20 übrig sind — sonst
        # würde z.B. bei "Samsung Galaxy S25" die Hülle vors Handy rutschen, weil
        # sie eher ein Deal-Signal hat als das Gerät selbst.
        sql = (f"SELECT asin, name, brand, image_url, current_price, tag FROM products "
               f"WHERE {conds} "
               f"ORDER BY is_active DESC, has_real_history DESC, deal_score DESC LIMIT 60")
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *tokens)

        # Zubehör (Hülle, Ladekabel, ...) hinter Kernprodukte einsortieren — außer
        # der Nutzer sucht selbst danach (z.B. "hülle" im Suchbegriff enthalten).
        # Stabile Sortierung erhält die bestehende Reihenfolge innerhalb der
        # beiden Gruppen (is_active/has_real_history/deal_score aus der Query).
        if not any(_ACCESSORY_RE.search(t) for t in tokens):
            rows = sorted(rows, key=lambda r: bool(_ACCESSORY_RE.search(r["name"] or "")))
        rows = rows[:20]
    else:
        rows = []

    def _result_item(r) -> str:
        img = f'<img src="{html.escape(r["image_url"])}" alt="" loading="lazy">' if r["image_url"] else ""
        name = html.escape((r["name"] or "Produkt")[:90])
        tag = f'<span class="r-tag">{html.escape(r["tag"])}</span>' if r["tag"] else ""
        price = ""
        if r["current_price"]:
            price_txt = f"{r['current_price']:.2f}".replace(".", ",")
            price = f'<span class="r-price">{price_txt} €</span>'
        return (f'<a href="https://www.snagga.de/preis/{r["asin"]}">{img}'
                f'<span class="r-main"><span class="r-name">{name}</span>{tag}</span>'
                f'<span class="r-side">{price}<span class="r-cue">{_CHART_ICON} Preisverlauf</span></span></a>')

    q_esc = html.escape(q[:60])
    if rows:
        items = "".join(_result_item(r) for r in rows)
        return _pc_shell(f"Preis-Check: {q[:60]}",
                         f"<h1>{len(rows)} Treffer f&uuml;r &bdquo;{q_esc}&ldquo;</h1>"
                         f'<div class="results">{items}</div>'
                         '<div class="hint">Genau dein Produkt nicht dabei? Füge oben den '
                         '<strong>Amazon-Link</strong> ein — dann prüfen wir es live und nehmen es auf.</div>')
    return _pc_shell("Noch nicht im Katalog",
                     f"<h1>&bdquo;{q_esc}&ldquo; haben wir noch nicht</h1>"
                     "<p>Wir bauen den Katalog laufend aus. Bis dein Produkt dabei ist: kopiere den "
                     "<strong>Amazon-Link</strong> in die Suchbox (z.B. <code>amazon.de/dp/…</code> oder "
                     "ein geteilter <code>amzn.eu</code>-Link) — dann prüfen wir den Preis sofort live "
                     "gegen die echte Preishistorie.</p>")


@app.api_route("/preis/{asin}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def price_page(request: Request, asin: str):
    """
    Dauerhafte Produkt-/Preisseite. Anders als /deal/{asin} läuft sie NIE ab und
    ist IMMER indexierbar — auch wenn gerade kein Deal aktiv ist. Sie rankt auf
    kaufnahe Suchanfragen ("{Produkt} Preisverlauf / günstigster Preis") und macht
    die bereits bezahlte Keepa-Preishistorie zum zweiten Mal nutzbar. Wachsender
    Seitenbestand statt ablaufender Deal-Seiten — dreht die SEO-Ökonomie um.

    On-Demand-Chart (Katalog-Architektur, siehe Memory): Der Großteil des
    Katalogs sind reine Stubs (Name+Eckdaten, keine Historie). Beim ersten Klick
    auf eine solche/veraltete Seite wird die Historie live geholt (1 Token) und
    gespeichert — rate-limitiert wie /preis-check, damit kein Missbrauch das
    Tagesbudget leert. Aktive Deals sind ausgenommen (schon stündlich geprüft).
    """
    if not re.match(r"^[A-Z0-9]{10}$", asin):
        return _not_found_page("Produkt nicht gefunden")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT asin, name, brand, image_url, current_price, original_price, "
            "all_time_low, avg_price, avg90_price, avg180_price, category, "
            "affiliate_url, is_active, rating, reviews, tag, has_real_history, "
            "last_checked "
            "FROM products WHERE asin=$1",
            asin,
        )
        if not row:
            return _not_found_page("Produkt nicht gefunden")

    stale = (row["last_checked"] is None
             or datetime.utcnow() - row["last_checked"] > timedelta(hours=PRICE_FRESH_HOURS))
    if not row["is_active"] and stale:
        ip = (request.headers.get("x-forwarded-for")
              or (request.client.host if request.client else "?")).split(",")[0].strip()
        if _pc_rate_ok(ip):
            await fetch_and_store_history(asin)
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT asin, name, brand, image_url, current_price, original_price, "
                    "all_time_low, avg_price, avg90_price, avg180_price, category, "
                    "affiliate_url, is_active, rating, reviews, tag, has_real_history, "
                    "last_checked "
                    "FROM products WHERE asin=$1",
                    asin,
                )
        # Bei Rate-Limit: einfach mit dem (evtl. veralteten) Stand weiterrendern —
        # fresh_check unten sorgt dafür, dass kein veralteter Preis gezeigt wird.

    async with pool.acquire() as conn:
        await conn.execute("UPDATE products SET last_viewed=$1 WHERE asin=$2", datetime.utcnow(), asin)
        hist = await conn.fetch(
            "SELECT price, timestamp FROM price_history WHERE asin=$1 ORDER BY id DESC LIMIT 2000",
            asin,
        )

    name      = html.escape((row["name"] or "Produkt")[:150])
    image     = html.escape(row["image_url"] or "https://www.snagga.de/favicon.svg")
    affiliate = html.escape(row["affiliate_url"] or f"https://www.amazon.de/dp/{asin}")
    category  = row["category"] or ""
    cat_esc   = html.escape(category)
    is_active = row["is_active"]

    # Zahlen, Urteil und Chart kommen aus derselben Quelle wie /produkt/{asin},
    # damit Modal und SSR-Preisseite garantiert identisch sind.
    detail = _compute_detail(row, hist)
    current, avg90, avg180, atl = detail["current"], detail["avg90"], detail["avg180"], detail["atl"]
    verdict, vcolor, vreason    = detail["verdict"], detail["vcolor"], detail["vreason"]
    chart_svg_90                = detail["chart_svg_90"]
    chart_svg                   = detail["chart_svg"]
    chart_svg_full              = detail["chart_svg_full"]

    def eur(v: float) -> str:
        return (f"{v:.2f}".replace(".", ",") + " €") if v and v > 0 else "—"

    # Indexierbar nur "gutes Zeug": aktiver Deal ODER Katalog-Quality. Dünne
    # No-Name-Seiten (Ramsch) bekommen noindex → raus aus Google (verhindert
    # Thin-Content-Abwertung der Domain); erreichbar bleiben sie trotzdem.
    indexable = is_active or is_catalog_quality(
        row["rating"] or 0, row["reviews"] or 0, row["brand"] or "", row["name"] or ""
    )
    robots = "index, follow" if indexable else "noindex, follow"

    canonical = f"https://www.snagga.de/preis/{asin}"
    title = f"{name} — Preisverlauf & Preis-Check | snagga.de"
    desc  = html.escape(
        f"Preisverlauf von {row['name'] or 'diesem Produkt'}: aktueller Preis {eur(current)}, "
        f"Allzeittief {eur(atl)}, 90-Tage-Schnitt {eur(avg90)}. Lohnt sich der Kauf gerade? snagga sagt es dir."
    )

    ld_json: dict = {
        "@context": "https://schema.org/",
        "@type":    "Product",
        "name":     (row["name"] or "Produkt")[:150],
        "image":    [row["image_url"]] if row["image_url"] else [],
        "category": category,
    }
    if row["brand"]:
        ld_json["brand"] = {"@type": "Brand", "name": row["brand"]}
    if current > 0:
        ld_json["offers"] = {
            "@type": "Offer", "url": canonical, "priceCurrency": "EUR",
            "price": f"{current:.2f}",
            "availability": "https://schema.org/InStock" if is_active else "https://schema.org/OutOfStock",
        }
    if row["rating"] and row["reviews"]:
        ld_json["aggregateRating"] = {
            "@type": "AggregateRating", "ratingValue": f"{row['rating']:.1f}", "reviewCount": int(row["reviews"]),
        }

    # Urteil "Guter Preis?" bei aktiven Deals ODER kürzlich live geprüften
    # Produkten (z.B. gerade über den Preis-Check nachgeschlagen). Bei länger
    # ungeprüften Produkten ist der gespeicherte Preis veraltet — ein Urteil
    # wäre irreführend (der aktuelle Amazon-Preis wird nicht mehr live geprüft).
    fresh_check = (row["last_checked"] is not None
                   and datetime.utcnow() - row["last_checked"] < timedelta(hours=PRICE_FRESH_HOURS))
    if (is_active or fresh_check) and current > 0:
        verdict_block = (f'<div class="verdict"><div class="v-head">Guter Preis gerade?</div>'
                         f'<div class="v-label">{verdict}</div>'
                         f'<div class="v-reason">{vreason}</div></div>')
    else:
        verdict_block = ''

    # CTA je nach Deal-Status. Kein Pfeil-Icon im Button (David-Wunsch: sauber
    # ohne Zusätze). "Aktiver Deal"-Nachsatz entfernt — der Kontext ergibt sich
    # aus dem Urteil-Badge darüber.
    if is_active and current > 0:
        cta = (f'<a class="cta cta-buy" href="{affiliate}" target="_blank" rel="nofollow noopener sponsored">'
               f'Zum Angebot bei Amazon</a>')
    elif fresh_check and current > 0:
        cta = (f'<a class="cta cta-buy" href="{affiliate}" target="_blank" rel="nofollow noopener sponsored">'
               f'Bei Amazon ansehen</a>'
               f'<p class="cta-note">Preis frisch geprüft — kein kuratierter Deal, aber die Zahlen oben sind aktuell.</p>')
    else:
        cta = ('<p class="cta-note" style="margin-top:0">Dieses Produkt ist gerade kein aktiver Deal. '
               'Sieh dir den Preisverlauf an und setz dir unten einen Preisalarm — wir schicken dir eine E-Mail, sobald der Preis fällt.</p>')

    # Preisalarm-Formular. Wunschpreis-Vorschlag: leicht unter dem aktuellen Preis,
    # sonst am Allzeittief orientiert.
    suggested = detail["suggested"]
    alert_form = f"""<h2>🔔 Preisalarm setzen</h2>
<form class="alert-form" method="post" action="https://www.snagga.de/alarm/setzen">
  <input type="hidden" name="asin" value="{asin}">
  <p class="alert-intro">Wir schicken dir eine E-Mail, sobald der Preis auf deinen Wunschpreis fällt. Kostenlos, jederzeit abbestellbar.</p>
  <div class="alert-row">
    <input type="email" name="email" required placeholder="deine@email.de" aria-label="E-Mail-Adresse">
    <input type="number" name="target_price" required min="1" step="0.01" value="{suggested}" placeholder="Wunschpreis €" aria-label="Wunschpreis in Euro">
    <button type="submit">Alarm aktivieren</button>
  </div>
  <p class="alert-legal">Du bekommst zuerst eine Bestätigungs-Mail (Double-Opt-in). Deine Adresse nutzen wir ausschließlich für diesen Preisalarm — siehe <a href="https://www.snagga.de/legal">Datenschutz</a>.</p>
</form>"""

    # "Aktueller Preis" ist eine Aktuellpreis-Aussage → nur bei last_checked<24h
    # zeigen (Amazon-Compliance, siehe Memory). Historische Werte (Tief, Ø) sind
    # keine Aktuellpreis-Aussage und bleiben unabhängig von der Frische erlaubt.
    _price_rows = [("Aktueller Preis", current)] if (is_active or fresh_check) else []
    stats_rows = "".join(
        f'<tr><td>{label}</td><td>{eur(val)}</td></tr>'
        for label, val in _price_rows + [
            ("Allzeittief", atl),
            ("Ø 90 Tage", avg90),
            ("Ø 180 Tage", avg180),
        ] if val and val > 0
    )

    # Ähnliche aktive Deals aus derselben Kategorie
    async with pool.acquire() as conn:
        similar = await conn.fetch(
            "SELECT asin, name, image_url, current_price, original_price, tag, category, brand, rating, reviews "
            "FROM products WHERE is_active=true AND category=$1 AND asin != $2 "
            "ORDER BY deal_score DESC LIMIT 4",
            category, asin,
        )
    similar_block = (
        f'<h2>Aktuelle Deals in {cat_esc}</h2><div class="grid">{"".join(_deal_card_html(r) for r in similar)}</div>'
        if similar else ""
    )
    cat_slug = SLUG_BY_CATEGORY.get(category)
    cat_link = (f'<p><a class="back" href="https://www.snagga.de/kategorie/{cat_slug}">{_arrow_icon("left")} Alle {cat_esc}-Deals</a></p>'
                if cat_slug else "")

    # Zeitraum-Umschalter: 90 Tage (Default, passt zum Ø90-Text) / 1 Jahr / Gesamt.
    # Tabs nur zeigen, wenn sich die Fenster tatsächlich unterscheiden — bei kurzer
    # History liefert _price_chart_svg für alle drei Fenster dieselbe Kurve.
    _chart_windows = [("90", "90 Tage", chart_svg_90), ("365", "1 Jahr", chart_svg), ("full", "Gesamt", chart_svg_full)]
    _distinct = len({svg for _, _, svg in _chart_windows if svg})
    if chart_svg_90 and _distinct > 1:
        _tabs = "".join(
            f'<button type="button" class="chart-tab{" active" if key == "90" else ""}" '
            f'data-target="chart-{key}" onclick="snaggaChartTab(this)">{label}</button>'
            for key, label, _ in _chart_windows
        )
        _panels = "".join(
            f'<div id="chart-{key}" style="{"" if key == "90" else "display:none"}">{svg}</div>'
            for key, _, svg in _chart_windows
        )
        chart_block = (
            f'<div class="chart"><div class="chart-tabs">{_tabs}</div>{_panels}</div>'
            "<script>function snaggaChartTab(btn){"
            "var bar=btn.parentElement;"
            "Array.prototype.forEach.call(bar.querySelectorAll('.chart-tab'),function(t){t.classList.remove('active')});"
            "btn.classList.add('active');"
            "['90','365','full'].forEach(function(k){"
            "var el=document.getElementById('chart-'+k);"
            "if(el)el.style.display=(btn.dataset.target==='chart-'+k)?'':'none';"
            "});}</script>"
        )
    elif chart_svg_90:
        chart_block = f'<div class="chart">{chart_svg_90}</div>'
    else:
        chart_block = '<p class="nochart">Der geprüfte Preisverlauf für dieses Produkt wird gerade aufgebaut — schau bald wieder vorbei.</p>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{image}">
<meta property="og:url" content="{canonical}">
<script type="application/ld+json">{json.dumps(ld_json, ensure_ascii=False)}</script>
<style>
  body {{ font-family: system-ui, sans-serif; background:#FAF8F5; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:1840px; width:98%; margin:0 auto; padding:32px 0; }}
  h1 {{ font-size:24px; line-height:1.35; margin:0 0 20px; }}
  h2 {{ font-size:19px; margin:36px 0 8px; }}
  .layout {{ display:grid; grid-template-columns:1fr 1.15fr; grid-template-rows:auto auto; grid-auto-flow:column; column-gap:28px; row-gap:36px; align-items:stretch; }}
  @media (max-width:820px) {{ .layout {{ grid-template-columns:1fr; grid-auto-flow:row; }} }}
  .col-left-top {{ display:flex; flex-direction:column; }}
  .col-right-top h2:first-child, .col-left-bottom h2:first-child, .col-right-bottom h2:first-child {{ margin-top:0; }}
  .prod-img {{ background:#fff; border:1px solid #EAE6E1; padding:18px; display:flex; align-items:center; justify-content:center; margin-bottom:16px; }}
  .prod-img img {{ max-width:100%; max-height:280px; object-fit:contain; }}
  .cta-note-bottom {{ margin-top:auto; }}
  .verdict {{ border-left:5px solid {vcolor}; background:#fff; padding:16px 20px; margin-bottom:16px; }}
  .verdict .v-head {{ font-size:13px; color:#7E7A75; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }}
  .verdict .v-label {{ font-size:24px; font-weight:800; color:{vcolor}; }}
  .verdict .v-reason {{ font-size:14px; color:#4A4845; margin-top:4px; }}
  .cta {{ display:block; text-align:center; padding:14px; font-weight:700; font-size:16px; text-decoration:none; }}
  .cta-buy {{ background:#C85E43; color:#fff; }}
  .cta-wait {{ background:#F2EFEA; color:#4A4845; }}
  .cta-note {{ font-size:12px; color:#7E7A75; margin:8px 0 0; }}
  .chart {{ background:#fff; border:1px solid #EAE6E1; padding:20px 18px; margin:8px 0 20px; }}
  .nochart {{ background:#fff; border:1px solid #EAE6E1; padding:20px; color:#7E7A75; font-size:14px; }}
  .chart-tabs {{ display:flex; gap:8px; margin-bottom:14px; }}
  .chart-tab {{ background:none; border:1px solid #EAE6E1; color:#153D68; padding:7px 16px; font-size:13px; font-family:inherit; cursor:pointer; }}
  .chart-tab.active {{ background:#153D68; color:#fff; border-color:#153D68; font-weight:600; }}
  table.stats {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #EAE6E1; margin-top:8px; }}
  table.stats td {{ padding:11px 16px; border-bottom:1px solid #EFEBE6; font-size:14px; }}
  table.stats tr:last-child td {{ border-bottom:none; }}
  table.stats td:first-child {{ color:#4A4845; }}
  table.stats td:last-child {{ text-align:right; font-weight:700; }}
  .alert-form {{ background:#fff; border:1px solid #D8D3CC; border-left:4px solid #C85E43; padding:22px 24px; margin:8px 0 8px; box-shadow:0 2px 10px rgba(0,0,0,0.05); }}
  .alert-intro {{ font-size:14px; color:#3A3835; margin:0 0 14px; }}
  .alert-row {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .alert-row input {{ flex:1; min-width:140px; padding:12px 14px; border:1.5px solid #B0A99D; color:#1F1E1D; font-size:15px; font-family:inherit; }}
  .alert-row input::placeholder {{ color:#8A8478; }}
  .alert-row input:focus {{ outline:none; border-color:#153D68; box-shadow:0 0 0 3px rgba(21,61,104,0.14); }}
  .alert-row input[type=number] {{ flex:0 0 150px; }}
  .alert-row button {{ background:#153D68; color:#fff; border:none; padding:12px 24px; font-size:15px; font-weight:700; cursor:pointer; }}
  .alert-row button:hover {{ background:#1b4d84; }}
  .alert-legal {{ font-size:11.5px; color:#6B6560; margin:12px 0 0; line-height:1.5; }}
  .alert-legal a {{ color:#6B6560; }}
  {_CARD_CSS}
  .back {{ display:inline-block; margin-top:20px; color:#153D68; }}
</style>
{_CARD_SHARE_JS}
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<div class="layout">
  <div class="col-left-top">
    <div class="prod-img"><img src="{image}" alt="{name}"></div>
    <h1>{name}</h1>
    {cta}
    <p class="cta-note cta-note-bottom">* Affiliate-Hinweis: Als Amazon-Partner verdienen wir an qualifizierten Käufen — für dich entstehen keine Mehrkosten. Der angezeigte Preis kann abweichen; massgeblich ist der Preis bei Amazon zum Kaufzeitpunkt.</p>
  </div>
  <div class="col-left-bottom">
    {alert_form}
  </div>
  <div class="col-right-top">
    {verdict_block}
    <h2>Preisverlauf</h2>
    {chart_block}
  </div>
  <div class="col-right-bottom">
    <h2>Preis-Eckdaten</h2>
    <table class="stats">{stats_rows}</table>
  </div>
</div>

{similar_block}
{cat_link}
<p><a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Alle aktuellen Deals</a></p>
</main>
{_CHART_HOVER_JS}
</body>
</html>""")


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _simple_page(heading: str, body_html: str, status: int = 200) -> HTMLResponse:
    """Schlichte, gebrandete Ergebnisseite (Alarm bestätigt/abgemeldet/Fehler)."""
    return HTMLResponse(status_code=status, content=f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{heading} | snagga.de</title>
<meta name="robots" content="noindex, follow">
<style>
  body {{ font-family: system-ui, sans-serif; background:#FAF8F5; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:620px; margin:0 auto; padding:48px 20px; }}
  h1 {{ font-size:24px; }}
  p {{ font-size:15px; line-height:1.6; color:#4A4845; }}
  .back {{ display:inline-block; margin-top:20px; color:#153D68; }}
</style>
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<h1>{heading}</h1>
{body_html}
<p><a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Zur Startseite</a></p>
</main>
</body>
</html>""")


@app.post("/alarm/setzen", response_class=HTMLResponse)
async def alarm_setzen(
    asin: str = Form(...),
    email: str = Form(...),
    target_price: float = Form(...),
    ajax: str = Form(default=""),
):
    """Nimmt einen Preisalarm entgegen und verschickt die Double-Opt-in-Bestätigung.

    Wird das Formular per fetch aus dem Produkt-Modal abgeschickt (ajax=1), kommt
    die Antwort als JSON zurück, damit der Nutzer die Seite nicht verlässt. Der
    klassische Formular-POST (SSR-Preisseite) liefert weiterhin eine HTML-Seite.
    """
    def _resp(heading: str, body_html: str, plain: str, status: int = 200):
        if ajax == "1":
            return JSONResponse({"ok": status == 200, "message": plain}, status_code=status)
        return _simple_page(heading, body_html, status=status)

    email = (email or "").strip().lower()
    if not re.match(r"^[A-Z0-9]{10}$", asin) or not _EMAIL_RE.match(email) or target_price <= 0:
        return _resp("Eingabe ungültig",
                     "<p>Bitte gib eine gültige E-Mail-Adresse und einen Wunschpreis größer 0 an.</p>",
                     "Bitte gib eine gültige E-Mail-Adresse und einen Wunschpreis größer 0 an.",
                     status=400)

    pool = await get_pool()
    async with pool.acquire() as conn:
        prod = await conn.fetchrow("SELECT name FROM products WHERE asin=$1", asin)
        if not prod:
            return _resp("Produkt nicht gefunden",
                         "<p>Zu diesem Produkt können wir keinen Alarm setzen.</p>",
                         "Zu diesem Produkt können wir keinen Alarm setzen.", status=404)

        # Missbrauchsschutz: max. 5 neue Alarme pro E-Mail in 10 Minuten
        recent = await conn.fetchval(
            "SELECT COUNT(*) FROM price_alerts WHERE email=$1 AND created_at > now() - interval '10 minutes'",
            email,
        )
        if recent and recent >= 5:
            return _resp("Zu viele Anfragen",
                         "<p>Du hast gerade viele Alarme gesetzt. Bitte versuch es in ein paar Minuten erneut.</p>",
                         "Du hast gerade viele Alarme gesetzt. Bitte versuch es in ein paar Minuten erneut.",
                         status=429)

        # Bestehende, noch nicht ausgelöste Alarme für dieselbe (E-Mail, ASIN)
        # ersetzen — Wunschpreis ändern statt Duplikate anzuhäufen.
        await conn.execute(
            "DELETE FROM price_alerts WHERE email=$1 AND asin=$2 AND notified_at IS NULL",
            email, asin,
        )
        token = secrets.token_urlsafe(32)
        await conn.execute(
            "INSERT INTO price_alerts (asin, email, target_price, token) VALUES ($1,$2,$3,$4)",
            asin, email, float(target_price), token,
        )

    sent = await alerts.send_confirmation(email, asin, prod["name"] or "dieses Produkt", float(target_price), token)
    if sent:
        return _resp("Fast geschafft! 📬",
                     f"<p>Wir haben dir eine Bestätigungs-Mail an <strong>{html.escape(email)}</strong> "
                     f"geschickt. Bitte klick den Link darin, dann ist dein Preisalarm aktiv.</p>"
                     f"<p style='font-size:13px;color:#7E7A75'>Keine Mail bekommen? Schau im Spam-Ordner nach.</p>",
                     f"Bestätigungs-Mail an {email} verschickt. Bitte klick den Link darin, dann ist dein Preisalarm aktiv. "
                     f"(Keine Mail? Schau im Spam-Ordner nach.)")
    return _resp("Preisalarm vorgemerkt",
                 "<p>Dein Alarm ist gespeichert, aber die Bestätigungs-Mail konnte gerade nicht versendet "
                 "werden. Bitte versuch es später noch einmal.</p>",
                 "Dein Alarm ist gespeichert, aber die Bestätigungs-Mail konnte gerade nicht versendet werden. "
                 "Bitte versuch es später noch einmal.", status=502)


@app.get("/alarm/bestaetigen", response_class=HTMLResponse)
async def alarm_bestaetigen(token: str = Query(default="")):
    """Double-Opt-in-Bestätigung: aktiviert den Alarm."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, confirmed FROM price_alerts WHERE token=$1", token)
        if not row:
            return _simple_page("Link ungültig",
                                "<p>Dieser Bestätigungslink ist ungültig oder abgelaufen.</p>", status=404)
        if not row["confirmed"]:
            await conn.execute(
                "UPDATE price_alerts SET confirmed=true, confirmed_at=now() WHERE id=$1", row["id"]
            )
    return _simple_page("Preisalarm aktiv ✅",
                        "<p>Dein Preisalarm ist jetzt aktiv. Wir melden uns per E-Mail, sobald dein Wunschpreis "
                        "erreicht ist. Jede Alarm-Mail enthält einen Abmeldelink.</p>")


@app.get("/alarm/abmelden", response_class=HTMLResponse)
async def alarm_abmelden(token: str = Query(default="")):
    """Abmeldung: löscht den Alarm dauerhaft."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await conn.execute("DELETE FROM price_alerts WHERE token=$1", token)
    if deleted and deleted.endswith("1"):
        return _simple_page("Abgemeldet",
                            "<p>Dein Preisalarm wurde gelöscht. Du bekommst dazu keine weiteren E-Mails.</p>")
    return _simple_page("Nichts zu tun",
                        "<p>Dieser Alarm existiert nicht (mehr).</p>")


@app.api_route("/prime-day", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def prime_day_page():
    """
    Dauerhafte Prime-Day-Landingpage. Die URL bleibt jedes Jahr gleich und
    baut so über die Jahre Ranking auf "Prime Day Deals" auf — vor dem Event
    Ratgeber-Inhalt (Fake-Rabatte erkennen), während des Events Live-Deals.
    Positionierung: snagga prüft jeden Rabatt gegen die echte Preishistorie.
    """
    canonical = "https://www.snagga.de/prime-day"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, name, image_url, current_price, original_price, tag, category, brand, rating, reviews "
            "FROM products WHERE is_active=true "
            "ORDER BY deal_score DESC LIMIT 24"
        )

    title = "Prime Day 2026: Nur echte Deals — geprüft gegen die Preishistorie | snagga.de"
    desc  = ("Nicht jeder Prime-Day-Rabatt ist echt. snagga prüft jedes Angebot gegen "
             "die tatsächliche Preishistorie: Allzeittief, 90-Tage-Durchschnitt, echter Rabatt.")

    deals_html = f'<div class="grid">{"".join(_deal_card_html(r) for r in rows)}</div>' if rows else ""

    ld_json = {
        "@context": "https://schema.org/",
        "@type":    "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name":  "Wie erkenne ich Fake-Rabatte am Prime Day?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text":  "Vergleiche den Angebotspreis mit der Preishistorie der letzten Monate, "
                             "nicht mit dem Streichpreis. Viele 'Rabatte' beziehen sich auf eine UVP, "
                             "die so nie verlangt wurde. snagga prüft jeden Deal automatisch gegen "
                             "Allzeittief und 90-Tage-Durchschnitt.",
                },
            },
            {
                "@type": "Question",
                "name":  "Wann ist der Amazon Prime Day 2026?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text":  "Amazon kündigt den Termin meist wenige Wochen vorher an — erfahrungsgemäß "
                             "liegt der Prime Day Mitte Juli. Die besten Deals gibt es oft schon in der "
                             "Woche davor.",
                },
            },
            {
                "@type": "Question",
                "name":  "Sind Prime-Day-Preise wirklich die günstigsten des Jahres?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text":  "Nicht immer. Manche Produkte sind am Prime Day auf Allzeittief, andere "
                             "waren wenige Wochen vorher günstiger. Entscheidend ist der Vergleich mit "
                             "der echten Preishistorie statt mit dem Streichpreis.",
                },
            },
        ],
    }
    ld_script = f'<script type="application/ld+json">{json.dumps(ld_json, ensure_ascii=False)}</script>'

    cat_nav = "".join(
        f'<a href="https://www.snagga.de/kategorie/{s}">{html.escape(n)}</a>'
        for s, n in CATEGORY_SLUGS.items()
    )

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
{ld_script}
<style>
  body {{ font-family: system-ui, sans-serif; background:#FAF8F5; color:#1F1E1D; margin:0; }}
  {_SITE_HEADER_CSS}
  main {{ max-width:1840px; width:98%; margin:0 auto; padding:32px 0; }}
  h1 {{ font-size:28px; margin-bottom:4px; }}
  h2 {{ font-size:21px; margin-top:40px; }}
  .lead {{ font-size:16px; max-width:820px; }}
  .tips {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:16px; margin:20px 0; }}
  .tip {{ background:#fff; padding:20px 22px; box-shadow:0 2px 10px rgba(0,0,0,0.04); }}
  .tip h3 {{ font-size:15px; margin:0 0 8px; }}
  .tip p {{ font-size:14px; margin:0; color:#4A4845; }}
  {_CARD_CSS}
  .catnav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:40px; }}
  .catnav a {{ font-size:13px; background:#fff; border-radius:20px; padding:6px 14px; text-decoration:none; color:#153D68; }}
  .back {{ display:inline-block; margin-top:20px; color:#153D68; }}
</style>
{_CARD_SHARE_JS}
</head>
<body>
{_SITE_HEADER_HTML}
<main>
<h1>Prime Day 2026: Nur echte Deals</h1>
<p class="lead">Am Prime Day glänzen viele Rabatte nur auf dem Papier: Der „−40%"-Streichpreis
wurde oft so nie verlangt. snagga prüft jedes Angebot automatisch gegen die <strong>echte
Preishistorie</strong> — Allzeittief, 90-Tage-Durchschnitt, tatsächliche Ersparnis. Hier landet
nur, was wirklich günstiger ist.</p>

<h2>So erkennst du Fake-Rabatte</h2>
<div class="tips">
  <div class="tip"><h3>📉 Preishistorie statt Streichpreis</h3>
  <p>Der Streichpreis ist meist die UVP — nicht der Preis, der zuletzt galt. Entscheidend ist,
  was das Produkt in den letzten 90 Tagen wirklich gekostet hat.</p></div>
  <div class="tip"><h3>🏆 Auf das Allzeittief achten</h3>
  <p>Ein Deal ist stark, wenn der Preis nahe am tiefsten je gemessenen Preis liegt — nicht,
  wenn die Prozentzahl gross ist.</p></div>
  <div class="tip"><h3>⏰ Nicht vom Countdown hetzen lassen</h3>
  <p>Künstliche Verknappung („nur noch 2 Stunden!") ist ein Verkaufstrick. Gute Preise kommen
  wieder — die Preishistorie zeigt, wie oft.</p></div>
  <div class="tip"><h3>⭐ Bewertungen ernst nehmen</h3>
  <p>Ein billiges Produkt mit 3 Sternen ist kein Deal. snagga listet nur Produkte mit
  mindestens 4 Sternen und 50+ Bewertungen.</p></div>
</div>

<h2>Aktuelle Top-Deals — gegen die Preishistorie geprüft</h2>
{deals_html}

<nav class="catnav">{cat_nav}</nav>
<p><a class="back" href="https://www.snagga.de/">{_arrow_icon('left')} Alle Deals ansehen</a></p>
</main>
</body>
</html>""")


@app.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def sitemap():
    """Dynamische Sitemap — jeder aktive Deal bekommt eine eigene, crawlbare URL."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, last_updated FROM products WHERE is_active=true ORDER BY deal_score DESC"
        )
        active_cats = {
            r["category"] for r in
            await conn.fetch("SELECT DISTINCT category FROM products WHERE is_active=true")
        }
        # Dauerhafte Preisseiten NUR für "gutes Zeug" (aktive Deals ODER
        # Katalog-Quality). Dünne No-Name-Seiten (Ramsch) kommen NICHT in die
        # Sitemap — sie sind zusätzlich per noindex ausgeschlossen (Thin Content
        # würde sonst Googles Qualitätsbild der Domain drücken).
        catalog_rows = await conn.fetch(
            "SELECT asin, last_updated, is_active, rating, reviews, brand, name "
            "FROM products ORDER BY is_active DESC, deal_score DESC"
        )
        all_products = [
            r for r in catalog_rows
            if r["is_active"] or is_catalog_quality(
                r["rating"] or 0, r["reviews"] or 0, r["brand"] or "", r["name"] or ""
            )
        ]

    urls = [
        "  <url><loc>https://www.snagga.de/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>",
        "  <url><loc>https://www.snagga.de/legal</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>",
        "  <url><loc>https://www.snagga.de/prime-day</loc><changefreq>daily</changefreq><priority>0.8</priority></url>",
    ]
    for slug, name in CATEGORY_SLUGS.items():
        if name in active_cats:
            urls.append(
                f"  <url><loc>https://www.snagga.de/kategorie/{slug}</loc>"
                f"<changefreq>daily</changefreq><priority>0.7</priority></url>"
            )
    for row in rows:
        lastmod = f"<lastmod>{row['last_updated'].date().isoformat()}</lastmod>" if row["last_updated"] else ""
        urls.append(
            f"  <url><loc>https://www.snagga.de/deal/{row['asin']}</loc>{lastmod}"
            f"<changefreq>daily</changefreq><priority>0.6</priority></url>"
        )
    for row in all_products:
        lastmod = f"<lastmod>{row['last_updated'].date().isoformat()}</lastmod>" if row["last_updated"] else ""
        urls.append(
            f"  <url><loc>https://www.snagga.de/preis/{row['asin']}</loc>{lastmod}"
            f"<changefreq>weekly</changefreq><priority>0.5</priority></url>"
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


@app.post("/admin/seed-bestsellers")
async def admin_seed_bestsellers(
    token: str = Query(default=""),
    max_tokens: int = Query(default=6000, ge=1, le=20000),
    max_per_cat: int = Query(default=400, ge=1, le=1000),
):
    """
    Loest einmalig den Bestseller-Seeding-Lauf aus (alle ~62 Kategorie-Knoten aus
    ROOTCAT_MAP). Admin-only. Standard-Budget 6000 Tokens (~20% Tagesbudget), Cap
    pro Kategorie 400 ASINs. Loggt Ergebnisse pro Kategorie ins JSON-Response.
    """
    _check_admin(token)
    from scraper import seed_bestsellers
    result = await seed_bestsellers(max_tokens=max_tokens, max_per_cat=max_per_cat)
    cache_clear()
    return result


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


# Referenzen auf laufende Hintergrund-Tasks halten (sonst Garbage-Collection)
_bg_tasks: set = set()


@app.api_route("/deep-sync", methods=["GET", "POST"])
async def trigger_deep_sync(token: str = Query(default="")):
    """Manueller Deep-Sync — holt echte Keepa-Historie, ersetzt Alt-/Fake-Daten,
    berechnet ATL/Ø neu und setzt has_real_history. Nur die Top-DEEPSYNC_LIMIT Deals.

    Läuft im HINTERGRUND und antwortet sofort: der Sync dauert mehrere Minuten und
    würde sonst am HTTP-Gateway-Timeout (502) scheitern. GET erlaubt (Browser-Link).
    """
    _check_admin(token)
    import asyncio
    from scraper import nightly_deep_sync

    async def _run():
        try:
            await nightly_deep_sync()
            cache_clear()
            print("[DEEP-SYNC] Hintergrund-Lauf fertig.")
        except Exception:
            import traceback
            print(f"[DEEP-SYNC ERROR] {traceback.format_exc()}")

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"message": "Deep-Sync gestartet — läuft im Hintergrund (~2-4 Min). "
                       "Danach zeigen die Top-Deal-Preisseiten echte Charts."}


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


@app.get("/debug/keepa-raw/{asin}")
async def debug_keepa_raw(asin: str, token: str = Query(default="")):
    """Zeigt für eine ASIN, welche Keepa-Preis-Typ-Indizes History (csv) und
    aktuelle Werte (stats.current) haben — zur Diagnose fehlender Charts."""
    _check_admin(token)
    import os, httpx
    KEEPA_KEY = os.getenv("KEEPA_API_KEY", "")
    if not KEEPA_KEY:
        return {"error": "no key"}
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.get("https://api.keepa.com/product",
                             params={"key": KEEPA_KEY, "domain": 3, "asin": asin,
                                     "stats": 1, "history": 1, "rating": 1})
        r.raise_for_status()
        data = r.json()
    prods = data.get("products") or []
    if not prods:
        return {"asin": asin, "found": False, "tokensConsumed": data.get("tokensConsumed")}
    p = prods[0]
    csv = p.get("csv") or []
    # Pro Index: Anzahl History-Punkte (jedes 2. Element ist ein Preis, -1 = kein Wert)
    NAMES = {0:"AMAZON",1:"NEW",2:"USED",3:"SALES",10:"NEW_FBA",11:"NEW_FBM",
             18:"BUYBOX",19:"USED_FBA",32:"BUYBOX_USED"}
    csv_points = {}
    for i, series in enumerate(csv):
        if isinstance(series, list) and series:
            pts = sum(1 for j in range(1, len(series), 2)
                      if isinstance(series[j], (int, float)) and series[j] > 0)
            if pts:
                csv_points[f"{i}:{NAMES.get(i,'?')}"] = pts
    stats = p.get("stats") or {}
    cur = stats.get("current") or []
    cur_vals = {f"{i}:{NAMES.get(i,'?')}": cur[i]
                for i in (0,1,2,10,11,18,19,32) if i < len(cur) and isinstance(cur[i],(int,float)) and cur[i] > 0}
    return {
        "asin": asin, "found": True,
        "tokensConsumed": data.get("tokensConsumed"),
        "csv_history_points_by_index": csv_points,
        "stats_current_by_index": cur_vals,
        "read_by_parse_product": "History+Preis nur aus 18/0/1 — alles andere wird ignoriert",
        "rootCategory": p.get("rootCategory"),
        "categoryTree": p.get("categoryTree"),
        "imagesCSV": p.get("imagesCSV"),
        "image_field": p.get("image"),
        "title": (p.get("title") or "")[:80],
        "brand": p.get("brand"),
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


@app.get("/test-mastodon")
async def test_mastodon(token: str = Query(default="")):
    _check_admin(token)
    import httpx
    from mastodon import MASTODON_INSTANCE, MASTODON_TOKEN, _build_status
    if not MASTODON_INSTANCE or not MASTODON_TOKEN:
        return {"ok": False, "error": "Env-Vars fehlen", "token_set": bool(MASTODON_TOKEN), "instance": MASTODON_INSTANCE}
    test_deal = {
        "asin":           "B0TEST00001",
        "name":           "snagga.de Mastodon-Test — alles funktioniert!",
        "current_price":  19.99,
        "original_price": 39.99,
        "deal_score":     999,
        "tag":            "Allzeittiefpreis",
        "category":       "Elektronik & Foto",
    }
    status = _build_status(test_deal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{MASTODON_INSTANCE}/api/v1/statuses",
                headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
                data={"status": status, "visibility": "public", "language": "de"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("id"):
                return {"ok": True, "message": "Test-Toot gesendet — schau auf deinem Profil!", "url": data.get("url")}
            return {"ok": False, "mastodon_error": data.get("error"), "status_code": resp.status_code}
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
