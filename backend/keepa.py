"""
Keepa API Client — liefert echte Preishistorien, Ratings und Produktdaten.
"""
import os
import asyncio
import httpx
from datetime import datetime

KEEPA_KEY  = os.getenv("KEEPA_API_KEY", "")
KEEPA_BASE = "https://api.keepa.com"
# Keepa-Epoch: Minuten seit Unix-Epoch bis 2011-01-01 00:00 UTC
KEEPA_EPOCH = 21564000

# Keepa domain-Codes für DACH — AT/CH haben kein eigenes Marketplace,
# daher alles über DE (domain=3)
COUNTRY_DOMAIN = {"DE": 3, "AT": 3, "CH": 3}


def _km_to_dt(km: int) -> datetime:
    """Keepa-Minuten → UTC datetime."""
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
    """Gibt den ersten positiven Wert aus arr an einem der gegebenen Indices zurück (in EUR)."""
    for idx in indices:
        if idx < len(arr):
            v = arr[idx]
            if isinstance(v, (int, float)) and v > 0:
                return round(v / 100.0, 2)
    return None


def _parse_product(p: dict) -> dict | None:
    """Wandelt ein Keepa-Produkt-Objekt in unser internes Format um."""
    asin = p.get("asin", "")
    if not asin:
        return None

    # Preishistorie: AMAZON (index 0) > NEW (index 1)
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

    # Stats-Block für Durchschnitts- und ATL-Preise
    stats  = p.get("stats") or {}
    atl    = stats.get("atl")    or []
    avg30  = stats.get("avg30")  or []
    avg90  = stats.get("avg90")  or []
    avg180 = stats.get("avg180") or []

    all_time_low   = _first_pos(atl,    0, 1) or current_price
    avg_price      = _first_pos(avg90,  0, 1) or _first_pos(avg30, 0, 1) or current_price
    original_price = _first_pos(avg180, 0, 1)

    # Originalpreis = höchster Preis der Historienkurve, falls avg180 fehlt
    if original_price is None or original_price <= current_price:
        prices = [h[0] for h in history if h[0] > 0]
        original_price = max(prices) if prices else round(current_price * 1.30, 2)
    if original_price < current_price:
        original_price = round(current_price * 1.20, 2)

    # Produktbild aus imagesCSV (kommagetrennte Dateinamen)
    imgs = p.get("imagesCSV") or ""
    first_img = imgs.split(",")[0].strip() if imgs else ""
    image_url = (
        f"https://images-na.ssl-images-amazon.com/images/I/{first_img}"
        if first_img else ""
    )

    # Rating: Keepa speichert als Integer × 10 (z.B. 46 = 4,6 Sterne)
    r_raw  = p.get("rating") or 0
    rating = round(r_raw / 10.0, 1) if r_raw > 0 else 0.0

    return {
        "title":          (p.get("title") or "").strip(),
        "brand":          (p.get("brand") or "").strip(),
        "image_url":      image_url,
        "current_price":  current_price,
        "original_price": original_price,
        "all_time_low":   all_time_low,
        "avg_price":      avg_price,
        "rating":         rating,
        "reviews":        p.get("reviewCount") or 0,
        "prime":          True,
        "history":        history,  # [(preis, datetime), …]
    }


async def enrich_with_keepa(
    asins: list[str],
    domain: int = 3,
    client: httpx.AsyncClient | None = None,
) -> dict[str, dict]:
    """
    Holt echte Produktdaten von Keepa für die gegebenen ASINs.
    Gibt {asin: enriched_data_dict} zurück.
    Bei fehlender KEEPA_API_KEY oder Fehler: leeres Dict.
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
                print(f"  Keepa: {len(data.get('products', []))} Produkte · {tokens} Tokens übrig")
            except Exception as e:
                print(f"  Keepa-Fehler (chunk {start}–{start+len(chunk)}): {e}")
                continue

            for p in data.get("products") or []:
                asin = p.get("asin", "")
                parsed = _parse_product(p)
                if parsed and asin:
                    results[asin] = parsed

            if start + 100 < len(asins):
                await asyncio.sleep(1.0)
    finally:
        if own_client:
            await client.aclose()

    return results
