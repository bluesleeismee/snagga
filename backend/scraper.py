"""
snagga.de — Deal-Pipeline
1. Keepa /deals  → ASIN-Discovery
2. Keepa /product → Deep-Sync (nachts / erste Befüllung)
3. Scoring + Hard Filters → 200 aktive + 100 Backup
4. PostgreSQL aktualisieren
"""
import re
import random
import asyncio
import httpx
from datetime import datetime, timedelta

from database import get_pool
from keepa import fetch_keepa_deals, enrich_with_keepa
from scoring import (
    CATEGORY_MAX_RANK,
    passes_hard_filters,
    calculate_deal_score,
    determine_tag,
)

AFFILIATE_TAG   = "snagga-21"
MAX_ACTIVE      = 200
MAX_BACKUP      = 100
TOP_PICKS_COUNT = 10
MIN_SCORE       = 40   # Deals unter diesem Score werden nicht angezeigt

CATEGORY_KEYWORDS = {
    "Elektronik": [
        "laptop", "notebook", "tablet", "smartphone", "handy", "kamera", "monitor",
        "drucker", "kopfhörer", "headphone", "headset", "tv", "fernseher", "lautsprecher",
        "speaker", "router", "modem", "festplatte", "ssd", "cpu", "grafikkarte",
        "maus", "tastatur", "keyboard", "mouse", "earbuds", "airpods", "kindle", "echo",
        "alexa", "fire", "powerbank", "ladekabel", "usb", "hdmi", "projektor",
    ],
    "Gaming": [
        "gaming", "playstation", "ps5", "ps4", "xbox", "nintendo", "switch", "controller",
        "konsole", "console", "gpu", "steam", "game", "spiel",
    ],
    "Haushalt": [
        "staubsauger", "vacuum", "saugroboter", "roomba", "reinigung",
        "waschmaschine", "geschirrspüler", "kühlschrank", "bügeleisen", "philips hue",
        "lampe", "glühbirne", "luftreiniger", "dyson",
    ],
    "Küche": [
        "blender", "mixer", "kaffeemaschine", "coffee", "küche", "topf",
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
    "Werkzeug": [
        "bohrmaschine", "akkuschrauber", "säge", "schleifer", "werkzeug", "tool",
        "hammer", "schraubendreher", "metabo", "makita", "bosch", "dewalt",
    ],
}


def classify_category(name: str) -> str:
    name_l = name.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_l for kw in keywords):
            return cat
    return "Sonstiges"


def generate_history(asin: str, current: float, avg: float, days: int = 60) -> list[tuple[float, datetime]]:
    """Simulierte Preishistorie als Fallback."""
    random.seed(asin)
    now = datetime.utcnow()
    history = []
    for i in range(days, -1, -1):
        ts = now - timedelta(days=i)
        price = (current + random.gauss(0, current * 0.005)) if i < 5 else \
                max(current * 0.9, round(avg + random.gauss(0, avg * 0.035), 2))
        history.append((round(price, 2), ts))
    return history


# ---------------------------------------------------------------------------
# Live-Preis-Check via Amazon-Seite (0 Tokens)
# ---------------------------------------------------------------------------

AMAZON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}

async def check_live_price(asin: str, client: httpx.AsyncClient) -> float | None:
    """Holt den aktuellen Preis von der Amazon-Seite. Gibt None bei Fehler zurück."""
    try:
        resp = await client.get(
            f"https://www.amazon.de/dp/{asin}",
            headers=AMAZON_HEADERS, follow_redirects=True, timeout=10,
        )
        if resp.status_code != 200:
            return None
        # Preis aus Schema.org JSON-LD oder meta
        m = re.search(r'"price"\s*:\s*"?(\d+[.,]\d{2})"?', resp.text)
        if m:
            return float(m.group(1).replace(",", "."))
        # Fallback: data-asin-price
        m = re.search(r'data-asin-price="(\d+[.,]\d{2})"', resp.text)
        if m:
            return float(m.group(1).replace(",", "."))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Haupt-Discovery-Job (stündlich)
# ---------------------------------------------------------------------------

async def fetch_and_update_deals():
    """
    Stündlicher Job:
    1. Keepa /deals → neue Kandidaten
    2. Hard Filters + Scoring
    3. Top 200 aktiv, Top 100 Backup, Top 10 als Top Picks
    4. DB aktualisieren
    """
    print(f"[{datetime.utcnow().isoformat()}] Starte stündliches Deal-Update …")
    now = datetime.utcnow()

    async with httpx.AsyncClient(timeout=30) as client:
        # ── 1. Keepa /deals ──────────────────────────────────────────────────
        raw_deals = await fetch_keepa_deals(
            domain=3, delta_pct=15, min_rating=40, min_reviews=50,
            date_range=24, per_page=150, client=client,
        )

        if not raw_deals:
            print("  Keepa /deals lieferte keine Daten — Abbruch.")
            return 0

        # ── 2. Hard Filters + Scoring ────────────────────────────────────────
        candidates = []
        for d in raw_deals:
            cat = classify_category(d["title"] or d["brand"])
            d["category"] = cat

            if not passes_hard_filters(
                d["rating"], d["reviews"], d["sales_rank"], cat,
                d["current_price"], d["avg90"], d["atl"],
            ):
                continue

            score, breakdown = calculate_deal_score(
                d["current_price"], d["avg90"], d["atl"],
                d["sales_rank"], cat,
                d["rating"], d["reviews"],
                price_updated=None,  # Timestamp unbekannt aus /deals
            )
            if score < MIN_SCORE:
                continue

            d["deal_score"]      = score
            d["score_breakdown"] = breakdown
            d["tag"]             = determine_tag(d["current_price"], d["atl"], d["avg90"], d["avg180"])
            d["original_price"]  = max(d["avg90"] or d["current_price"] * 1.25,
                                       d["current_price"] * 1.10)
            d["avg_price"]       = d["avg90"] or d["current_price"]
            candidates.append(d)

        # Sortieren nach Score
        candidates.sort(key=lambda x: x["deal_score"], reverse=True)
        active_pool = candidates[:MAX_ACTIVE]
        backup_pool = candidates[MAX_ACTIVE : MAX_ACTIVE + MAX_BACKUP]

        print(f"  {len(candidates)} qualifiziert · {len(active_pool)} aktiv · {len(backup_pool)} Backup")

        # ── 3. DB schreiben ──────────────────────────────────────────────────
        db = await get_pool()
        async with db.acquire() as conn:

            # Alle bisherigen Deals deaktivieren
            await conn.execute("UPDATE products SET is_active=false, is_backup=false, is_top_pick=false")

            for i, p in enumerate(active_pool + backup_pool):
                is_active   = i < len(active_pool)
                is_backup   = not is_active
                is_top_pick = is_active and i < TOP_PICKS_COUNT
                asin        = p["asin"]

                await conn.execute("""
                    INSERT INTO products
                      (asin, name, brand, image_url, category,
                       current_price, original_price, all_time_low, avg_price,
                       avg90_price, avg180_price,
                       deal_score, rating, reviews, prime,
                       last_updated, last_checked, affiliate_url,
                       is_active, is_backup, is_top_pick, is_fba,
                       sales_rank, tag, score_breakdown)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                            $16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
                    ON CONFLICT (asin) DO UPDATE SET
                        name            = EXCLUDED.name,
                        brand           = EXCLUDED.brand,
                        image_url       = EXCLUDED.image_url,
                        category        = EXCLUDED.category,
                        current_price   = EXCLUDED.current_price,
                        original_price  = EXCLUDED.original_price,
                        all_time_low    = EXCLUDED.all_time_low,
                        avg_price       = EXCLUDED.avg_price,
                        avg90_price     = EXCLUDED.avg90_price,
                        avg180_price    = EXCLUDED.avg180_price,
                        deal_score      = EXCLUDED.deal_score,
                        rating          = EXCLUDED.rating,
                        reviews         = EXCLUDED.reviews,
                        last_updated    = EXCLUDED.last_updated,
                        last_checked    = EXCLUDED.last_checked,
                        affiliate_url   = EXCLUDED.affiliate_url,
                        is_active       = EXCLUDED.is_active,
                        is_backup       = EXCLUDED.is_backup,
                        is_top_pick     = EXCLUDED.is_top_pick,
                        is_fba          = EXCLUDED.is_fba,
                        sales_rank      = EXCLUDED.sales_rank,
                        tag             = EXCLUDED.tag,
                        score_breakdown = EXCLUDED.score_breakdown
                """,
                    asin, (p["title"] or "")[:200], p["brand"], p["image_url"], p["category"],
                    p["current_price"], p["original_price"], p["atl"] or p["current_price"], p["avg_price"],
                    p["avg90"] or 0.0, p["avg180"] or 0.0,
                    p["deal_score"], p["rating"], p["reviews"], True,
                    now, now,
                    f"https://www.amazon.de/dp/{asin}?tag={AFFILIATE_TAG}",
                    is_active, is_backup, is_top_pick, p["is_fba"],
                    p["sales_rank"] or 0, p["tag"], p["score_breakdown"],
                )

                # Preispunkt in Historik
                await conn.execute(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    asin, p["current_price"], now.isoformat(),
                )

                # Simulierte Historik wenn noch keine vorhanden
                count = await conn.fetchval("SELECT COUNT(*) FROM price_history WHERE asin=$1", asin)
                if count <= 1:
                    sim = generate_history(asin, p["current_price"], p["avg_price"])
                    await conn.executemany(
                        "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                        [(asin, pr, ts.isoformat()) for pr, ts in sim],
                    )

    print(f"  Fertig: {len(active_pool)} aktiv, {len(backup_pool)} Backup, "
          f"{min(TOP_PICKS_COUNT, len(active_pool))} Top Picks")
    return len(active_pool)


# ---------------------------------------------------------------------------
# Stündlicher Preis-Check der aktiven Deals
# ---------------------------------------------------------------------------

async def hourly_price_check():
    """
    Prüft die aktuellen Preise aller aktiven Deals via Amazon-Seite.
    Deals deren Preis nicht mehr gut ist → deaktivieren, Backup nachrücken.
    """
    print(f"[{datetime.utcnow().isoformat()}] Stündlicher Preis-Check …")
    db  = await get_pool()
    now = datetime.utcnow()

    async with db.acquire() as conn:
        active = await conn.fetch(
            "SELECT asin, current_price, avg90_price, all_time_low, category, "
            "rating, reviews, sales_rank FROM products WHERE is_active=true ORDER BY deal_score DESC"
        )

    deactivated = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for row in active:
            asin      = row["asin"]
            live_price = await check_live_price(asin, client)
            await asyncio.sleep(0.5)  # sanftes Rate-Limiting

            if live_price is None:
                continue  # Bei Fehler: behalten

            # Score mit aktuellem Preis neu berechnen
            score, breakdown = calculate_deal_score(
                live_price,
                row["avg90_price"] or row["current_price"],
                row["all_time_low"] or live_price,
                row["sales_rank"] or 0,
                row["category"],
                row["rating"],
                row["reviews"],
                price_updated=now,
            )

            async with db.acquire() as conn:
                if score < MIN_SCORE:
                    # Deal ist nicht mehr gut — deaktivieren
                    await conn.execute(
                        "UPDATE products SET is_active=false, is_top_pick=false, "
                        "deal_score=$2, last_checked=$3 WHERE asin=$1",
                        asin, score, now,
                    )
                    deactivated += 1
                else:
                    tag = determine_tag(
                        live_price,
                        row["all_time_low"] or 0,
                        row["avg90_price"] or 0,
                        0,
                    )
                    await conn.execute(
                        "UPDATE products SET current_price=$2, deal_score=$3, "
                        "tag=$4, last_checked=$5, score_breakdown=$6 WHERE asin=$1",
                        asin, live_price, score, tag, now, breakdown,
                    )
                    await conn.execute(
                        "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                        asin, live_price, now.isoformat(),
                    )

    if deactivated > 0:
        await _promote_backups(deactivated)

    # Top Picks neu setzen
    await _recalculate_top_picks()
    print(f"  Preis-Check fertig: {deactivated} deaktiviert.")


async def _promote_backups(count: int):
    """Rückt bis zu `count` Backup-Deals nach Live vor (mit Preis-Verifikation)."""
    db = await get_pool()
    async with db.acquire() as conn:
        backups = await conn.fetch(
            "SELECT asin, current_price, avg90_price, all_time_low, category, "
            "rating, reviews, sales_rank FROM products "
            "WHERE is_backup=true ORDER BY deal_score DESC LIMIT $1",
            count * 2,
        )

    promoted = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for row in backups:
            if promoted >= count:
                break
            asin       = row["asin"]
            live_price = await check_live_price(asin, client)
            await asyncio.sleep(0.5)

            if live_price is None:
                continue

            score, _ = calculate_deal_score(
                live_price,
                row["avg90_price"] or row["current_price"],
                row["all_time_low"] or live_price,
                row["sales_rank"] or 0,
                row["category"],
                row["rating"],
                row["reviews"],
            )

            if score >= MIN_SCORE:
                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE products SET is_active=true, is_backup=false, "
                        "current_price=$2, deal_score=$3, last_checked=$4 WHERE asin=$1",
                        asin, live_price, score, datetime.utcnow(),
                    )
                promoted += 1
                print(f"    ↑ Backup {asin} promoviert (Score {score})")


async def _recalculate_top_picks():
    """Setzt die Top 10 nach aktuellem Score als Top Picks."""
    db = await get_pool()
    async with db.acquire() as conn:
        await conn.execute("UPDATE products SET is_top_pick=false")
        await conn.execute(
            "UPDATE products SET is_top_pick=true WHERE asin IN "
            "(SELECT asin FROM products WHERE is_active=true ORDER BY deal_score DESC LIMIT $1)",
            TOP_PICKS_COUNT,
        )


# ---------------------------------------------------------------------------
# Nächtlicher Deep-Sync (03:00 Uhr) via Keepa /product
# ---------------------------------------------------------------------------

async def nightly_deep_sync():
    """
    Aktualisiert alle aktiven + Backup-Deals vollständig via Keepa /product:
    Preishistorie, Sales Rank, Ø-Preise, ATL, Rating, Reviews, Bilder.
    """
    print(f"[{datetime.utcnow().isoformat()}] Nachtlicher Deep-Sync …")
    db = await get_pool()

    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin FROM products WHERE is_active=true OR is_backup=true"
        )
    asins = [r["asin"] for r in rows]
    if not asins:
        print("  Keine Deals für Deep-Sync gefunden.")
        return

    print(f"  Deep-Sync für {len(asins)} ASINs …")
    keepa_data = await enrich_with_keepa(asins, domain=3)
    now        = datetime.utcnow()

    async with db.acquire() as conn:
        for asin, kd in keepa_data.items():
            score, breakdown = calculate_deal_score(
                kd["current_price"], kd["avg90_price"], kd["all_time_low"],
                kd["sales_rank"], "Sonstiges",  # Kategorie aus DB holen wenn nötig
                kd["rating"], kd["reviews"],
                price_updated=now,
            )
            tag = determine_tag(kd["current_price"], kd["all_time_low"],
                                kd["avg90_price"], kd["avg180_price"])

            await conn.execute("""
                UPDATE products SET
                    current_price   = $2,
                    original_price  = $3,
                    all_time_low    = $4,
                    avg_price       = $5,
                    avg90_price     = $6,
                    avg180_price    = $7,
                    rating          = $8,
                    reviews         = $9,
                    sales_rank      = $10,
                    is_fba          = $11,
                    deal_score      = $12,
                    tag             = $13,
                    score_breakdown = $14,
                    last_checked    = $15,
                    image_url       = CASE WHEN $16 != '' THEN $16 ELSE image_url END
                WHERE asin = $1
            """,
                asin,
                kd["current_price"], kd["original_price"], kd["all_time_low"],
                kd["avg_price"], kd["avg90_price"], kd["avg180_price"],
                kd["rating"], kd["reviews"], kd["sales_rank"], kd["is_fba"],
                score, tag, breakdown, now, kd["image_url"],
            )

            # Echte Preishistorie einmalig befüllen (≤ 2 existierende Punkte)
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM price_history WHERE asin=$1", asin
            )
            if kd["history"] and existing <= 2:
                recent = kd["history"][-365:]
                await conn.executemany(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    [(asin, pr, ts.isoformat()) for pr, ts in recent],
                )
                print(f"    ✓ {asin}: {len(recent)} echte Preispunkte")

    # Deaktiviere Deals mit Score < 40
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE products SET is_active=false, is_top_pick=false "
            "WHERE is_active=true AND deal_score < $1", MIN_SCORE
        )

    await _recalculate_top_picks()
    print(f"  Deep-Sync fertig: {len(keepa_data)} Produkte aktualisiert.")
