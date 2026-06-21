"""
CamelCamelCamel RSS Parser + Deal Scoring
Läuft täglich um 03:00 Uhr und befüllt die SQLite-Datenbank.
"""
import re
import random
import hashlib
import httpx
import feedparser
import aiosqlite
from datetime import datetime, timedelta

from database import DB_PATH

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
            "image_url": f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.L.jpg",
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
                        "image_url": f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.L.jpg",
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

    # In DB schreiben
    async with aiosqlite.connect(DB_PATH) as db:
        for p in products:
            await db.execute("""
                INSERT OR REPLACE INTO products
                (asin, name, brand, image_url, category, current_price, original_price,
                 all_time_low, avg_price, deal_score, rating, reviews, prime,
                 last_updated, affiliate_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                p["asin"], p["name"], p["brand"], p["image_url"], p["category"],
                p["current_price"], p["original_price"], p["all_time_low"], p["avg_price"],
                p["deal_score"], p["rating"], p["reviews"], p["prime"],
                p["last_updated"], p["affiliate_url"],
            ))

            # Preispunkt hinzufügen
            await db.execute(
                "INSERT INTO price_history (asin, price, timestamp) VALUES (?,?,?)",
                (p["asin"], p["current_price"], p["last_updated"]),
            )

            # Simulierte Historie für neue Produkte anlegen (nur wenn noch keine vorhanden)
            row = await (await db.execute(
                "SELECT COUNT(*) FROM price_history WHERE asin=?", (p["asin"],)
            )).fetchone()
            if row and row[0] <= 1:
                history = generate_history(p["asin"], p["current_price"], p["avg_price"])
                await db.executemany(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES (?,?,?)",
                    [(p["asin"], price, ts) for price, ts in history],
                )

        await db.commit()

    print(f"  Fertig: {len(products)} Produkte gespeichert.")
    return len(products)
