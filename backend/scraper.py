"""
CamelCamelCamel RSS Parser + Deal Scoring
Läuft täglich um 03:00 Uhr und befüllt die PostgreSQL-Datenbank.
"""
import re
import random
import hashlib
import asyncio
import httpx
import feedparser
from datetime import datetime, timedelta

from database import get_pool

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

AFFILIATE_TAG = "snagga-21"

RSS_FEEDS = [
    "https://camelcamelcamel.com/top_drops/rss?market=de",
    "https://de.camelcamelcamel.com/top_drops/rss",
    "https://camelcamelcamel.com/new_lows/rss?market=de",
]

CATEGORY_KEYWORDS = {
    "Elektronik": [
        "laptop", "notebook", "tablet", "smartphone", "handy", "kamera", "monitor",
        "drucker", "kopfhörer", "headphone", "headset", "tv", "fernseher", "lautsprecher",
        "speaker", "router", "modem", "festplatte", "ssd", "cpu", "processor", "grafikkarte",
        "maus", "tastatur", "keyboard", "mouse", "earbuds", "airpods", "kindle", "echo",
        "alexa", "fire", "powerbank", "ladekabel", "usb", "hdmi", "projektor",
    ],
    "Gaming": [
        "gaming", "playstation", "ps5", "ps4", "xbox", "nintendo", "switch", "controller",
        "konsole", "console", "gpu", "grafik", "steam", "game", "spiel",
    ],
    "Haushalt": [
        "staubsauger", "vacuum", "saugroboter", "roomba", "reinigung", "cleaning",
        "waschmaschine", "geschirrspüler", "kühlschrank", "bügeleisen", "philips hue",
        "lampe", "lamp", "glühbirne", "luftreiniger", "dyson",
    ],
    "Küche": [
        "blender", "mixer", "kaffeemaschine", "coffee", "kochen", "küche", "topf",
        "pfanne", "messer", "airfryer", "friteuse", "nespresso", "thermomix",
        "wasserkocher", "toaster", "mikrowelle",
    ],
    "Sport": [
        "sport", "fitness", "laufen", "fahrrad", "bike", "yoga", "training",
        "hantel", "dumbbell", "treadmill", "laufband", "fitbit", "garmin",
    ],
    "Beauty": [
        "beauty", "kosmetik", "pflege", "parfum", "shampoo", "haarpflege",
        "skincare", "creme", "rasierer", "epilator",
    ],
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def classify_category(name: str) -> str:
    name_l = name.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_l for kw in keywords):
            return cat
    return "Sonstiges"


def extract_asin(url: str) -> str | None:
    for pattern in [
        r"/product/([A-Z0-9]{10})",
        r"/dp/([A-Z0-9]{10})",
        r"/([A-Z0-9]{10})(?:[/?]|$)",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def parse_prices(title: str, description: str) -> tuple[float, float]:
    """Extrahiert (aktueller Preis, Originalpreis) aus Titel oder Beschreibung."""
    for text in [description, title]:
        prices = re.findall(r"€\s*(\d{1,4}[.,]\d{2})", text)
        if len(prices) >= 2:
            p0 = float(prices[0].replace(",", "."))
            p1 = float(prices[1].replace(",", "."))
            return (min(p0, p1), max(p0, p1))
        if len(prices) == 1:
            p = float(prices[0].replace(",", "."))
            return p, round(p * 1.30, 2)
    return 0.0, 0.0


def seeded_random(asin: str, offset: float = 0.0) -> float:
    """Deterministischer Zufallswert 0–1 basierend auf ASIN."""
    h = int(hashlib.md5((asin + str(offset)).encode()).hexdigest(), 16)
    return (h % 10000) / 10000.0


def calculate_score(current: float, original: float, asin: str) -> tuple[int, float, float]:
    """Berechnet (deal_score, all_time_low, avg_price)."""
    if original <= 0 or current <= 0:
        return 50, current, current
    # Simulierte Preishistorie basierend auf Original
    r = seeded_random(asin)
    all_time_low = round(original * (0.58 + r * 0.18), 2)   # 58–76 % des Originals
    avg_price    = round(original * (0.87 + seeded_random(asin, 1) * 0.10), 2)  # 87–97 %

    if current < all_time_low:
        all_time_low = current

    denom = avg_price - all_time_low
    if denom <= 0:
        denom = 0.01
    score = 100 - ((current - all_time_low) / denom * 100)
    score = max(0, min(100, int(score)))
    return score, all_time_low, avg_price


def generate_history(asin: str, current: float, avg: float, days: int = 60) -> list[tuple[float, str]]:
    """Generiert simulierte Preishistorie für den Mini-Chart."""
    random.seed(asin)
    now = datetime.utcnow()
    history = []
    for i in range(days, -1, -1):
        ts = (now - timedelta(days=i)).isoformat()
        if i < 5:
            price = current + random.gauss(0, current * 0.005)
        else:
            noise = random.gauss(0, avg * 0.035)
            price = avg + noise
        price = max(current * 0.9, round(price, 2))
        history.append((price, ts))
    return history


# ---------------------------------------------------------------------------
# Amazon Produktbild via og:image
# ---------------------------------------------------------------------------

AMAZON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8",
}

FALLBACK_IMG_PATTERN = re.compile(r"images-na\.ssl-images-amazon\.com/images/P/")

async def fetch_amazon_image(asin: str, client: httpx.AsyncClient) -> str:
    """Holt die og:image URL von der Amazon-Produktseite."""
    try:
        url = f"https://www.amazon.de/dp/{asin}"
        resp = await client.get(url, headers=AMAZON_HEADERS, follow_redirects=True, timeout=10)
        if resp.status_code != 200:
            return ""
        # og:image extrahieren
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://[^"\']+)["\']', resp.text)
        if m:
            return m.group(1)
        # Fallback: data-old-hires oder landingImage
        m = re.search(r'"large":"(https://m\.media-amazon\.com/images/I/[^"]+)"', resp.text)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"  Bild für {asin} nicht ladbar: {e}")
    return ""


async def enrich_images(products: list[dict], client: httpx.AsyncClient) -> None:
    """Ergänzt fehlende oder Fallback-Bild-URLs für alle Produkte."""
    needs_image = [p for p in products if not p["image_url"] or FALLBACK_IMG_PATTERN.search(p["image_url"])]
    if not needs_image:
        return
    print(f"  Hole Bilder für {len(needs_image)} Produkte …")
    for p in needs_image:
        img = await fetch_amazon_image(p["asin"], client)
        if img:
            p["image_url"] = img
            print(f"    ✓ {p['asin']}: {img[:60]}…")
        await asyncio.sleep(1.2)  # Rate-Limiting — 1 Request/Sekunde


# ---------------------------------------------------------------------------
# Seed-Daten (Fallback wenn RSS nicht erreichbar)
# ---------------------------------------------------------------------------

def get_seed_data() -> list[dict]:
    now = datetime.utcnow().isoformat()
    raw = [
        ("B09XS7JWHH", "Sony WH-1000XM5 Noise Cancelling Kopfhörer",       "Sony",      248.90, 379.99, "Elektronik", 4.7, 8432),
        ("B0BDHWDR12", "Apple AirPods Pro (2. Generation)",                  "Apple",     189.00, 279.00, "Elektronik", 4.8, 12500),
        ("B0BJLT98Q7", "Apple iPad (10. Generation) 64 GB Wi-Fi",            "Apple",     379.00, 529.00, "Elektronik", 4.6, 5200),
        ("B09GZ93GFG", "Dyson V15 Detect Absolute Kabelloser Staubsauger",   "Dyson",     499.00, 699.00, "Haushalt",   4.5, 3100),
        ("B098RL6SBJ", "Nintendo Switch OLED-Modell mit weißem Joy-Con",     "Nintendo",  299.00, 349.99, "Gaming",     4.8, 15000),
        ("B08H99BPJN", "Sony DualSense Wireless Controller",                  "Sony",       49.99,  69.99, "Gaming",     4.7, 22000),
        ("B0B6FJVL85", "Nespresso Vertuo Pop Kaffeekapselmaschine",          "Nespresso",  59.99, 109.99, "Küche",      4.5, 4200),
        ("B07KW1QHBB", "Philips Hue White & Color Ambiance Starter Set",     "Philips",   119.99, 179.99, "Haushalt",   4.6, 6800),
        ("B09JCQD7V6", "adidas Ultraboost 22 Laufschuhe",                   "adidas",     89.95, 189.95, "Sport",      4.4, 2300),
        ("B0C8K3JZP6", "Samsung 65\" QLED 4K Q60C Smart TV",               "Samsung",   699.00, 999.00, "Elektronik", 4.3, 1800),
    ]
    products = []
    for asin, name, brand, current, original, cat, rating, reviews in raw:
        score, low, avg = calculate_score(current, original, asin)
        products.append({
            "asin": asin, "name": name, "brand": brand,
            "image_url": f"https://ws-eu.amazon-adsystem.com/widgets/q?_encoding=UTF8&ASIN={asin}&Format=_SL500_&ID=AsinImage&MarketPlace=DE&ServiceVersion=20070822&WS=1&tag={AFFILIATE_TAG}",
            "category": cat,
            "current_price": current, "original_price": original,
            "all_time_low": low, "avg_price": avg,
            "deal_score": score, "rating": rating, "reviews": reviews,
            "prime": 1, "last_updated": now,
            "affiliate_url": f"https://www.amazon.de/dp/{asin}?tag={AFFILIATE_TAG}",
        })
    return products


# ---------------------------------------------------------------------------
# Haupt-Job
# ---------------------------------------------------------------------------

async def fetch_and_update_deals():
    """Ruft CCC RSS ab und aktualisiert die DB. Fallback auf Seed-Daten."""
    print(f"[{datetime.utcnow().isoformat()}] Starte Deal-Update …")
    products: list[dict] = []
    seen_asins: set[str] = set()

    headers = {"User-Agent": "Mozilla/5.0 (compatible; Snagga/1.0)"}
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
        for url in RSS_FEEDS:
            try:
                resp = await client.get(url)
                feed = feedparser.parse(resp.text)
                entries = feed.entries

                for entry in entries[:60]:
                    link  = getattr(entry, "link", "")
                    asin  = extract_asin(link)
                    if not asin or asin in seen_asins:
                        continue
                    seen_asins.add(asin)

                    title = getattr(entry, "title", "")
                    desc  = getattr(entry, "description", "") or getattr(entry, "summary", "")

                    # Produktname: Alles vor dem ersten " - " (CCC fügt oft "Best price …" an)
                    name = re.sub(r"\s*[-–]\s*(Best price|Lowest|Dropped|Gesunken|New low).*", "",
                                  title, flags=re.IGNORECASE).strip() or title[:100]

                    current, original = parse_prices(title, desc)
                    if current <= 0 or original <= 0:
                        continue
                    if original < current:
                        original = current * 1.25

                    score, low, avg = calculate_score(current, original, asin)
                    if score < 40:
                        continue

                    products.append({
                        "asin": asin, "name": name, "brand": "",
                        "image_url": f"https://ws-eu.amazon-adsystem.com/widgets/q?_encoding=UTF8&ASIN={asin}&Format=_SL500_&ID=AsinImage&MarketPlace=DE&ServiceVersion=20070822&WS=1&tag={AFFILIATE_TAG}",
                        "category": classify_category(name),
                        "current_price": current, "original_price": original,
                        "all_time_low": low, "avg_price": avg,
                        "deal_score": score,
                        "rating": round(3.8 + seeded_random(asin, 2) * 1.1, 1),
                        "reviews": int(50 + seeded_random(asin, 3) * 4950),
                        "prime": 1,
                        "last_updated": datetime.utcnow().isoformat(),
                        "affiliate_url": f"https://www.amazon.de/dp/{asin}?tag={AFFILIATE_TAG}",
                    })

                if products:
                    print(f"  {len(products)} Produkte von {url}")
                    break

            except Exception as e:
                print(f"  Feed {url} fehlgeschlagen: {e}")

    if not products:
        print("  RSS nicht erreichbar — nutze Seed-Daten")
        products = get_seed_data()

    # Produktbilder ergänzen (og:image von Amazon)
    async with httpx.AsyncClient(timeout=15) as img_client:
        await enrich_images(products, img_client)

    # In PostgreSQL schreiben
    db = await get_pool()
    async with db.acquire() as conn:
        for p in products:
            await conn.execute("""
                INSERT INTO products
                (asin, name, brand, image_url, category, current_price, original_price,
                 all_time_low, avg_price, deal_score, rating, reviews, prime,
                 last_updated, affiliate_url)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT (asin) DO UPDATE SET
                    name          = EXCLUDED.name,
                    brand         = EXCLUDED.brand,
                    image_url     = EXCLUDED.image_url,
                    category      = EXCLUDED.category,
                    current_price = EXCLUDED.current_price,
                    original_price= EXCLUDED.original_price,
                    all_time_low  = EXCLUDED.all_time_low,
                    avg_price     = EXCLUDED.avg_price,
                    deal_score    = EXCLUDED.deal_score,
                    rating        = EXCLUDED.rating,
                    reviews       = EXCLUDED.reviews,
                    prime         = EXCLUDED.prime,
                    last_updated  = EXCLUDED.last_updated,
                    affiliate_url = EXCLUDED.affiliate_url
            """,
                p["asin"], p["name"], p["brand"], p["image_url"], p["category"],
                p["current_price"], p["original_price"], p["all_time_low"], p["avg_price"],
                p["deal_score"], p["rating"], p["reviews"], p["prime"],
                p["last_updated"], p["affiliate_url"],
            )

            # Aktuellen Preispunkt hinzufügen
            await conn.execute(
                "INSERT INTO price_history (asin, price, timestamp) VALUES ($1, $2, $3)",
                p["asin"], p["current_price"], p["last_updated"],
            )

            # Simulierte Historie nur für neue Produkte
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM price_history WHERE asin=$1", p["asin"]
            )
            if count <= 1:
                history = generate_history(p["asin"], p["current_price"], p["avg_price"])
                await conn.executemany(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1, $2, $3)",
                    [(p["asin"], price, ts) for price, ts in history],
                )

    print(f"  Fertig: {len(products)} Produkte gespeichert.")
    return len(products)
