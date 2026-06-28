"""
Keepa API Client — /deals für ASIN-Discovery, /product für Deep-Sync.
"""
import os
import json
import asyncio
import httpx
from datetime import datetime

KEEPA_KEY  = os.getenv("KEEPA_API_KEY", "")
KEEPA_BASE = "https://api.keepa.com"
# Keepa epoch: Minuten von Unix-Epoch bis 2011-01-01 00:00 UTC
KEEPA_EPOCH = 21_564_000


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _km_to_dt(km: int) -> datetime:
    return datetime.utcfromtimestamp((km + KEEPA_EPOCH) * 60)


def _parse_flat_csv(flat: list) -> list[tuple[float, datetime]]:
    """[km, cents, km, cents, …] → [(preis_eur, datetime), …]"""
    out = []
    for i in range(0, len(flat) - 1, 2):
        cents = flat[i + 1]
        if not isinstance(cents, (int, float)) or cents <= 0:
            continue
        out.append((round(cents / 100.0, 2), _km_to_dt(int(flat[i]))))
    return out


def _first_pos(arr: list, *indices) -> float | None:
    for idx in indices:
        if idx < len(arr):
            v = arr[idx]
            if isinstance(v, (int, float)) and v > 0:
                return round(v / 100.0, 2)
    return None


# ---------------------------------------------------------------------------
# /deals — ASIN-Discovery
# ---------------------------------------------------------------------------

async def fetch_keepa_deals(
    domain:      int   = 3,
    delta_pct:   int   = 15,    # mind. X% Preissenkung
    min_rating:  int   = 40,    # 4.0 Sterne × 10
    min_reviews: int   = 50,    # nach Empfang gefiltert
    page:        int   = 0,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """
    Ruft den Keepa /deal Endpoint ab.
    Gibt Liste von Deal-Dicts zurück: asin, title, brand, image_url,
    current_price, avg30, avg90, avg180, atl, sales_rank, rating, reviews,
    is_fba, delta_pct
    """
    if not KEEPA_KEY:
        return []

    # Keepa Deal-Finder: priceTypes als Integer (0 = alle Typen)
    # deltaPercentRange: [min, max], negative = Preissenkung in %
    # dateRange: 0=24h, 1=2 Tage, ... 6=7 Tage
    # Whitelist: nur Deals aus diesen Amazon-DE Kategorien (root + Level-1-Subcats)
    # IDs ermittelt via /debug/category-children (2026-06-28, DE domain)
    INCLUDE_CAT_IDS = [
        # Auto & Motorrad
        78191031, 79899031, 80931031,
        # Baumarkt + Garten (10925031 war fälschlich als Gewerbe markiert)
        80084031, 80085031, 84144031, 83122031,
        10925031, 10925241, 10930941, 124540011,
        # Computer & Zubehör
        340843031, 340844031, 368180031, 368181031, 368182031,
        # Drogerie & Körperpflege + Kosmetik
        64187031, 64257031, 5787997031, 65633031, 64980031,
        84230031, 84231031, 129371031, 129369031, 129368031,
        # Elektro-Großgeräte
        908823031, 908824031, 908825031,
        # Elektronik & Foto
        562066, 569604, 578112, 725718, 124538011,
        # Games
        300992, 541708, 526742, 124544011,
        # Beleuchtung + Küche, Haushalt & Wohnen
        213083031, 213084031, 227218031,
        3167641, 3169011, 3312441, 3842901,
        # Musikinstrumente & DJ-Equipment
        340849031, 340850031,
        # Sport & Freizeit
        16435051, 16435121, 16435061, 16435111,
    ]
    selection = {
        "page":                page,
        "domainId":            domain,
        "priceTypes":          0,                   # 0 = alle Preistypen
        "deltaPercentRange":   [-100, -delta_pct],  # mind. X% gefallen
        "dateRange":           0,                   # letzte 24 Stunden
        "minRating":           min_rating,          # 40 = 4.0 Sterne (×10)
        "hasReviews":          True,
        "isFilterEnabled":     True,
        "filterErotic":        True,
        "sortType":            1,                   # 1 = nach deltaPercent
        "includeCategories":   INCLUDE_CAT_IDS,    # Whitelist statt Blacklist
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)

    try:
        resp = await client.get(
            f"{KEEPA_BASE}/deal",
            params={
                "key":       KEEPA_KEY,
                "selection": json.dumps(selection, separators=(',', ':')),
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Keepa /deal Fehler: {e}")
        return []
    finally:
        if own_client:
            await client.aclose()

    tokens    = data.get("tokensLeft", "?")
    # Response-Struktur: data["deals"]["dr"] = Array der Deal-Objekte
    deals_obj = data.get("deals") or {}
    raw_deals = deals_obj.get("dr") or []
    print(f"  Keepa /deal: {len(raw_deals)} Kandidaten · {tokens} Tokens übrig")
    # rootCat-Verteilung loggen (hilft beim Aufbau des includeCategories-Filters)
    if raw_deals:
        from collections import Counter
        cat_counts = Counter(d.get("rootCat", 0) for d in raw_deals)
        print(f"  rootCat-Verteilung (Top 15): {cat_counts.most_common(15)}")
    # Keepa Preis-Typ-Indices (aus constants.py):
    # 0=AMAZON, 1=NEW, 3=SALES_RANK, 7=NEW_FBM, 10=NEW_FBA
    # 16=RATING(×10), 17=COUNT_REVIEWS, 18=BUY_BOX_SHIPPING
    IDX_AMAZON   = 0
    IDX_SALES    = 3
    IDX_NEW_FBA  = 10
    IDX_RATING   = 16
    IDX_REVIEWS  = 17
    IDX_BUYBOX   = 18

    def _cv(arr, idx):
        """Holt Wert aus Keepa-Array, gibt 0 zurück wenn nicht verfügbar."""
        if arr and idx < len(arr):
            v = arr[idx]
            return v if isinstance(v, (int, float)) and v > 0 else 0
        return 0

    def _cv_best(arr):
        """Bester Preis aus Keepa-Array: BuyBox > Amazon > NEW_FBA (in Cent)."""
        return _cv(arr, IDX_BUYBOX) or _cv(arr, IDX_AMAZON) or _cv(arr, IDX_NEW_FBA)

    def c2e(v):
        """Cent → EUR, 0 wenn ungültig."""
        return round(v / 100.0, 2) if v > 0 else 0.0

    results = []
    for d in raw_deals:
        asin = d.get("asin", "")
        if not asin:
            continue

        # current[] = aktueller Preisarray (Cent)
        cur_arr = d.get("current") or []

        # Bester aktueller Preis: Buy Box > Amazon direkt
        current = c2e(_cv(cur_arr, IDX_BUYBOX) or _cv(cur_arr, IDX_AMAZON) or _cv(cur_arr, IDX_NEW_FBA))
        if current <= 0:
            continue

        # avg[] = Liste von Perioden-Arrays: [30d, 90d, 180d, 365d]
        # Jedes Perioden-Array ist ein Preis-Typ-Array → besten verfügbaren Preis nehmen
        avg_arr = d.get("avg") or []
        avg30  = c2e(_cv_best(avg_arr[0]) if len(avg_arr) > 0 else 0)
        avg90  = c2e(_cv_best(avg_arr[1]) if len(avg_arr) > 1 else 0)
        avg180 = c2e(_cv_best(avg_arr[2]) if len(avg_arr) > 2 else 0)
        # 365d-Ø als ATL-Proxy (besser als nichts)
        atl = c2e(_cv_best(avg_arr[3]) if len(avg_arr) > 3 else 0) or avg180

        # Rating: current[16] ist Rating × 10 (z.B. 45 = 4.5 Sterne)
        rating  = round(_cv(cur_arr, IDX_RATING) / 10.0, 1)
        reviews = _cv(cur_arr, IDX_REVIEWS)

        # Sales Rank: current[3]
        sales_rank = _cv(cur_arr, IDX_SALES)

        # FBA-Proxy: NEW_FBA Preis > 0
        is_fba = _cv(cur_arr, IDX_NEW_FBA) > 0 or _cv(cur_arr, IDX_BUYBOX) > 0

        # Image: Array von ASCII-Codes → Dateiname
        img_raw = d.get("image") or []
        if isinstance(img_raw, list) and img_raw:
            img_file = "".join(chr(c) for c in img_raw if isinstance(c, int))
            image_url = f"https://images-na.ssl-images-amazon.com/images/I/{img_file}"
        else:
            image_url = f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg"

        # deltaPercent: auch ein Array [30d, 90d, 180d, 365d] von Preis-Typ-Arrays
        dp_arr = d.get("deltaPercent") or []
        dp = _cv_best(dp_arr[0]) if dp_arr else 0

        results.append({
            "asin":          asin,
            "title":         (d.get("title") or "").strip(),
            "brand":         "",        # Deal-Endpoint gibt keine Brand
            "image_url":     image_url,
            "current_price": current,
            "avg30":         avg30,
            "avg90":         avg90,
            "avg180":        avg180,
            "atl":           atl,
            "sales_rank":    sales_rank,
            "rating":        rating,
            "reviews":       reviews,
            "is_fba":        is_fba,
            "delta_pct":     dp,
            "root_cat":      d.get("rootCat", 0),
        })

    return results


# ---------------------------------------------------------------------------
# /product — Deep-Sync (vollständige Anreicherung)
# ---------------------------------------------------------------------------

def _parse_product(p: dict) -> dict | None:
    asin = p.get("asin", "")
    if not asin:
        return None

    # Preishistorie: AMAZON (0) > NEW (1)
    csv = p.get("csv") or []
    history: list[tuple[float, datetime]] = []
    for idx in (0, 1):
        if idx < len(csv) and csv[idx]:
            history = _parse_flat_csv(csv[idx])
            if history:
                break

    if not history:
        return None

    current_price = history[-1][0]

    stats  = p.get("stats") or {}
    atl    = stats.get("atl")    or []
    avg30  = stats.get("avg30")  or []
    avg90  = stats.get("avg90")  or []
    avg180 = stats.get("avg180") or []

    all_time_low   = _first_pos(atl,    0, 1) or current_price
    avg_price      = _first_pos(avg90,  0, 1) or _first_pos(avg30, 0, 1) or current_price
    avg90_price    = _first_pos(avg90,  0, 1) or current_price
    avg180_price   = _first_pos(avg180, 0, 1) or current_price
    original_price = avg180_price

    if original_price < current_price:
        prices = [h[0] for h in history if h[0] > 0]
        original_price = max(prices) if prices else round(current_price * 1.25, 2)
    if original_price < current_price:
        original_price = round(current_price * 1.20, 2)

    # Bild
    imgs = p.get("imagesCSV") or ""
    first = imgs.split(",")[0].strip() if imgs else ""
    image_url = f"https://images-na.ssl-images-amazon.com/images/I/{first}" if first else ""

    # Rating
    r_raw  = p.get("rating") or 0
    rating = round(r_raw / 10.0, 1) if r_raw > 0 else 0.0

    # Sales Rank
    sr_csv = csv[3] if len(csv) > 3 and csv[3] else []
    sales_rank = 0
    if sr_csv:
        last_valid = [(sr_csv[i+1]) for i in range(0, len(sr_csv)-1, 2) if sr_csv[i+1] and sr_csv[i+1] > 0]
        sales_rank = last_valid[-1] if last_valid else 0

    # FBA-Proxy: Buy-Box-Shipping = 0
    bb_ship_csv = csv[14] if len(csv) > 14 and csv[14] else []
    is_fba = False
    if bb_ship_csv:
        last_ship = [(bb_ship_csv[i+1]) for i in range(0, len(bb_ship_csv)-1, 2)
                     if isinstance(bb_ship_csv[i+1], (int, float)) and bb_ship_csv[i+1] >= 0]
        if last_ship:
            is_fba = last_ship[-1] == 0

    return {
        "title":          (p.get("title") or "").strip(),
        "brand":          (p.get("brand") or "").strip(),
        "image_url":      image_url,
        "current_price":  current_price,
        "original_price": original_price,
        "all_time_low":   all_time_low,
        "avg_price":      avg_price,
        "avg90_price":    avg90_price,
        "avg180_price":   avg180_price,
        "rating":         rating,
        "reviews":        p.get("reviewCount") or 0,
        "sales_rank":     sales_rank,
        "is_fba":         is_fba,
        "prime":          True,
        "history":        history,
    }


async def enrich_with_keepa(
    asins:  list[str],
    domain: int = 3,
    client: httpx.AsyncClient | None = None,
) -> dict[str, dict]:
    """
    Deep-Sync: vollständige Produktdaten für eine Liste von ASINs.
    Gibt {asin: data_dict} zurück.
    """
    if not KEEPA_KEY or not asins:
        return {}

    results: dict[str, dict] = {}
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=45)

    try:
        for start in range(0, len(asins), 100):
            chunk = asins[start : start + 100]
            try:
                resp = await client.get(
                    f"{KEEPA_BASE}/product",
                    params={
                        "key":     KEEPA_KEY,
                        "domain":  domain,
                        "asin":    ",".join(chunk),
                        "stats":   1,
                        "history": 1,
                        "rating":  1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                tokens = data.get("tokensLeft", "?")
                print(f"  Keepa /product: {len(data.get('products', []))} · {tokens} Tokens übrig")
            except Exception as e:
                print(f"  Keepa /product Fehler (chunk {start}): {e}")
                continue

            for p in data.get("products") or []:
                asin   = p.get("asin", "")
                parsed = _parse_product(p)
                if parsed and asin:
                    results[asin] = parsed

            if start + 100 < len(asins):
                await asyncio.sleep(1.0)
    finally:
        if own_client:
            await client.aclose()

    return results
