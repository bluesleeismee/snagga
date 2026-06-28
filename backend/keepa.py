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

    # Nur offiziell gültige Felder (aus DEAL_REQUEST_KEYS der keepa lib):
    # deltaPercentRange: [min, max] — negative Werte = Preissenkung
    # dateRange: 0=24h, 1=2 Tage, 2=3 Tage, ... 6=7 Tage
    selection = {
        "page":               page,
        "domainId":           domain,
        "priceTypes":         [0, 1],              # 0=Amazon, 1=New
        "deltaPercentRange":  [-100, -delta_pct],  # mind. X% gefallen
        "dateRange":          0,                   # letzte 24 Stunden
        "minRating":          min_rating,          # z.B. 40 = 4.0 Sterne
        "hasReviews":         True,
        "isFilterEnabled":    True,
        "filterErotic":       True,
        "sortType":           1,                   # 1 = nach deltaPercent sortiert
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
    if raw_deals:
        import json as _json
        print(f"  DEBUG erstes Deal-Objekt keys: {list(raw_deals[0].keys())}")
        print(f"  DEBUG erstes Deal-Objekt: {_json.dumps(raw_deals[0], default=str)[:500]}")

    results = []
    for d in raw_deals:
        asin = d.get("asin", "")
        if not asin:
            continue

        # Preis in Cent → EUR
        def c2e(v): return round(v / 100.0, 2) if isinstance(v, (int, float)) and v > 0 else 0.0

        current   = c2e(d.get("currentPrice") or d.get("current") or 0)
        avg30     = c2e(d.get("avg30",  0))
        avg90     = c2e(d.get("avg90",  0))
        avg180    = c2e(d.get("avg180", 0))
        atl       = c2e(d.get("atl",   0))

        if current <= 0:
            continue

        # Image
        img_file = d.get("img", "") or d.get("image", "")
        image_url = (
            f"https://images-na.ssl-images-amazon.com/images/I/{img_file}"
            if img_file else
            f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg"
        )

        # Rating × 10 → float
        r_raw  = d.get("rating") or 0
        rating = round(r_raw / 10.0, 1) if r_raw > 0 else 0.0

        # FBA-Proxy: buyBoxSeller is Amazon oder bbIsAmazon flag
        is_fba = bool(
            d.get("bbIsAmazon") or
            d.get("isFBA") or
            d.get("priceType") == 0  # Preis kam von Amazon direkt
        )

        results.append({
            "asin":        asin,
            "title":       (d.get("title") or "").strip(),
            "brand":       (d.get("brand") or "").strip(),
            "image_url":   image_url,
            "current_price": current,
            "avg30":       avg30,
            "avg90":       avg90,
            "avg180":      avg180,
            "atl":         atl,
            "sales_rank":  d.get("salesRank") or d.get("currentSalesRank") or 0,
            "rating":      rating,
            "reviews":     d.get("reviews") or d.get("reviewCount") or 0,
            "is_fba":      is_fba,
            "delta_pct":   d.get("deltaPercent") or 0,
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
