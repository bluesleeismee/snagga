"""
snagga.de — Deal-Pipeline
1. Keepa /deals  → ASIN-Discovery
2. Keepa /product → Deep-Sync (nachts / erste Befüllung)
3. Scoring + Hard Filters → 200 aktive + 100 Backup
4. PostgreSQL aktualisieren
"""
import os
import re
import json
import random
import asyncio
import httpx
from datetime import datetime, timedelta

from database import get_pool
from keepa import fetch_keepa_deals, enrich_with_keepa, fetch_current_prices, ELECTRONICS_CAT_IDS
from scoring import (
    CATEGORY_MAX_RANK,
    passes_hard_filters,
    calculate_deal_score,
    determine_tag,
)

AFFILIATE_TAG   = "snagga-21"  # Fallback-Tag für Kategorien ohne eigenen Tracking-Tag

# Optional: pro Kategorie ein eigener Amazon-Tracking-Tag, um Klicks/Verkäufe
# im Partnerprogramm-Dashboard nach Kategorie getrennt auszuwerten.
# Format env var (JSON): {"Elektronik & Foto": "snagga-elektronik-21", ...}
try:
    CATEGORY_TAGS: dict[str, str] = json.loads(os.getenv("AMAZON_CATEGORY_TAGS", "{}"))
except (json.JSONDecodeError, TypeError):
    CATEGORY_TAGS = {}


def _affiliate_tag_for(category: str) -> str:
    return CATEGORY_TAGS.get(category, AFFILIATE_TAG)


MAX_ACTIVE      = 500
MAX_BACKUP      = 150
TOP_PICKS_COUNT = 10
MIN_SCORE       = 30
MIN_PRICE       = 20.0
DEAL_PAGES      = 16    # 16 × 150 = 2.400 Kandidaten/Run
ELECTRONICS_PAGES = 6   # Zusatzabfrage nur Elektronik/Geräte (−10 %), ~6 Tokens/Run
DEEPSYNC_LIMIT  = 500   # Deep-Sync deckt den ganzen aktiven Bestand ab (~283).
                        # Muss die Zahl aktiver Deals übersteigen, sonst bleiben
                        # niedriger gerankte Produkte dauerhaft ohne Chart. History
                        # wird nur für Produkte ohne echte Historie geholt (Token-
                        # schonend, siehe nightly_deep_sync), daher unkritisch hoch.

CATEGORY_MIN_PRICE: dict[str, float] = {
    "Elektronik & Foto":                 25.0,
    "Computer & Zubehör":                25.0,
    "Elektro-Großgeräte":                50.0,
    "Kamera & Foto":                     30.0,
    "Musikinstrumente & DJ-Equipment":   30.0,
    "Baumarkt":                          28.0,
    "Küche, Haushalt & Wohnen":          28.0,
}

# ---------------------------------------------------------------------------
# Amazon-DE rootCat-ID → Snagga-Kategorie
# Aus Debug-Endpoint /debug/keepa-cats ermittelt (150 Deals, 2026-06-28)
# ---------------------------------------------------------------------------
ROOTCAT_MAP: dict[int, str] = {
    # Auto & Motorrad (78191031 war fälschlich in EXCLUDE_ROOTCATS!)
    78191031:    "Auto & Motorrad",
    79899031:    "Auto & Motorrad",
    80931031:    "Auto & Motorrad",
    77:          "Auto & Motorrad",
    # Baumarkt
    80084031:    "Baumarkt",
    80084:       "Baumarkt",
    80085031:    "Baumarkt",
    84144031:    "Baumarkt",
    83122031:    "Baumarkt",
    # Garten (10925031 war fälschlich in EXCLUDE_ROOTCATS als Gewerbe!)
    10925031:    "Baumarkt",
    10925241:    "Baumarkt",
    10930941:    "Baumarkt",
    124540011:   "Baumarkt",
    # Computer & Zubehör
    340843031:   "Computer & Zubehör",
    340844031:   "Computer & Zubehör",
    368180031:   "Computer & Zubehör",
    368181031:   "Computer & Zubehör",
    368182031:   "Computer & Zubehör",
    541966:      "Computer & Zubehör",
    # Drogerie & Körperpflege + Kosmetik
    64187031:    "Drogerie & Körperpflege",
    64257031:    "Drogerie & Körperpflege",
    5787997031:  "Drogerie & Körperpflege",
    65633031:    "Drogerie & Körperpflege",
    64980031:    "Drogerie & Körperpflege",
    64117011:    "Drogerie & Körperpflege",
    84230031:    "Drogerie & Körperpflege",
    84231031:    "Drogerie & Körperpflege",
    129371031:   "Drogerie & Körperpflege",
    129369031:   "Drogerie & Körperpflege",
    129368031:   "Drogerie & Körperpflege",
    # Elektro-Großgeräte
    908823031:   "Elektro-Großgeräte",
    908824031:   "Elektro-Großgeräte",
    908825031:   "Elektro-Großgeräte",
    # Elektronik & Foto
    562066:      "Elektronik & Foto",
    569604:      "Elektronik & Foto",
    578112:      "Elektronik & Foto",
    725718:      "Elektronik & Foto",
    124538011:   "Elektronik & Foto",
    4185211:     "Elektronik & Foto",
    # Games
    300992:      "Games",
    541708:      "Games",
    526742:      "Games",
    124544011:   "Games",
    296676011:   "Games",
    # Kamera & Foto
    571860:      "Kamera & Foto",
    # Beleuchtung + Küche, Haushalt & Wohnen
    213083031:   "Küche, Haushalt & Wohnen",
    213084031:   "Küche, Haushalt & Wohnen",
    227218031:   "Küche, Haushalt & Wohnen",
    3167641:     "Küche, Haushalt & Wohnen",
    3375251:     "Küche, Haushalt & Wohnen",
    3667441:     "Küche, Haushalt & Wohnen",
    3169011:     "Küche, Haushalt & Wohnen",
    3312441:     "Küche, Haushalt & Wohnen",
    3842901:     "Küche, Haushalt & Wohnen",
    # Musikinstrumente & DJ-Equipment
    340849031:   "Musikinstrumente & DJ-Equipment",
    340850031:   "Musikinstrumente & DJ-Equipment",
    3382071:     "Musikinstrumente & DJ-Equipment",
    # Sport & Freizeit (16435051 war fälschlich als Drogerie eingetragen!)
    16435051:    "Sport & Freizeit",
    16435121:    "Sport & Freizeit",
    16435061:    "Sport & Freizeit",
    16435111:    "Sport & Freizeit",
    16435731:    "Sport & Freizeit",
}

# Explizit ausschließen (rootCat → None, egal was Keywords sagen)
EXCLUDE_ROOTCATS: set[int] = {
    11961464031,  # Bekleidung / Fashion
    340846031,    # Lebensmittel & Getränke
    12950651,     # Spielzeug
    186606,       # Bücher
    340852031,    # Heimtier
    284266,       # Film/Video/DVD
    255882,       # Musik-Tonträger (Vinyl, CDs)
    355007011,    # Taschen & Accessoires
    5866098031,   # Gewerbe/Industrie (Präzisionslager etc.)
    192416031,    # Bürobedarf (Stempel, Büromaterial)
}

# Keyword-Fallback NUR für bekannte Produkte (exhaustiv, kein Catch-all)
KEYWORD_MAP: dict[str, list[str]] = {
    "Elektronik & Foto": [
        "laptop", "notebook", "tablet", "smartphone", "monitor", "bildschirm",
        "kopfhörer", "headphones", "headset", "lautsprecher", "soundbar",
        "fernseher", " tv ", "beamer", "projektor", "router", "access point",
        "festplatte", "ssd", "grafikkarte", "gpu", "cpu", "prozessor",
        "tastatur", "keyboard", "maus", "mouse", "webcam", "mikrofon",
        "powerbank", "ladegerät", "usb-hub", "hdmi", "kindle", "e-reader",
        "echo dot", "fire tv", "apple watch", "airpods", "earbuds",
        "drucker", "scanner", "nas", "ups",
    ],
    "Computer & Zubehör": [
        "computer", "pc ", "desktop", "mini-pc", "stick pc",
        "ram ", "arbeitsspeicher", "mainboard", "netzteil", "gehäuse tower",
    ],
    "Kamera & Foto": [
        "kamera", "camera", "objektiv", "lens", "spiegelreflex", "dslr",
        "mirrorless", "systemkamera", "gopro", "action cam", "stativ",
        "blitzgerät", "drohne", "drone",
    ],
    "Games": [
        "playstation", "ps5", "ps4", "xbox", "nintendo switch",
        "gaming headset", "gaming maus", "gaming tastatur", "gaming stuhl",
        "gaming monitor", "controller",
    ],
    "Baumarkt": [
        "bohrmaschine", "akkuschrauber", "säge", "schleifer", "flex ",
        "hammer", "schraubendreher", "werkzeug", "metabo", "makita",
        "bosch", "dewalt", "festool", "hilti", "kärcher", "hochdruckreiniger",
        "malerrolle", "farbe ", "klebeband profi", "schrauben set",
    ],
    "Drogerie & Körperpflege": [
        "elektrische zahnbürste", "oral-b", "sonicare", "haartrockner",
        "föhn", "glätteisen", "lockenstab", "rasierer", "elektrorasierer",
        "epilator", "epilierer", "rasierklinge", "parfum", "deo ",
    ],
    "Küche, Haushalt & Wohnen": [
        "kaffeemaschine", "kaffeevollautomat", "nespresso", "dolce gusto",
        "airfryer", "heißluftfritteuse", "mikrowelle", "toaster", "wasserkocher",
        "mixer", "blender", "küchenmaschine", "thermomix", "staubsauger",
        "saugroboter", "roomba", "dampfbügeleisen", "luftreiniger",
        "luftbefeuchter", "heizlüfter", "ventilator", "standventilator",
    ],
    "Elektro-Großgeräte": [
        "waschmaschine", "trockner", "geschirrspüler", "kühlschrank",
        "gefrierbox", "gefrierschrank", "herd ", "backofen", "induktionskochfeld",
    ],
    "Sport & Freizeit": [
        "fahrrad", "e-bike", "mountainbike", "laufrad", "scooter",
        "fitnessgerät", "laufband", "crosstrainer", "ergometer", "rudergerät",
        "hantel", "kettlebell", "yogamatte", "garmin", "fitbit",
        "sportschuhe", "laufschuhe",
    ],
    "Musikinstrumente & DJ-Equipment": [
        "gitarre", "keyboard piano", "klavier", "schlagzeug", "mikrofon xlr",
        "kopfhörer studio", "audio interface", "midi", "synthesizer",
        "lautsprecher pa", "dj controller",
    ],
    "Auto & Motorrad": [
        "dashcam", "navigationssystem", "navi ", "obd2", "autoreinigung",
        "autopflege", "dachbox", "fahrradträger auto",
    ],
}

# Ausschluss-Keywords: egal was rootCat sagt, diese Produkte nie anzeigen
EXCLUDE_KEYWORDS = [
    "papier", "druckerpapier", "bastelfilz", "filz ", "plüsch", "kuscheltier",
    "spielzeug", "puppe ", "lego ", "puzzle", "brettspiel", "kartenspiel",
    "buch ", "bücher", "roman ", "unterwäsche", "unterhose", "socken",
    "t-shirt", "jeans", "hose ", "jacke ", "pullover", "kleidung",
    "schuhe ", "sneaker ", "handtuch", "bettwäsche", "kissen ", "decke ",
    "nahrungsergänzung", "protein pulver", "vitamine", "kapsel ",
    "lebensmittel", "kaffee bohnen", "tee ", "gewürze",
    # Intime / erotische Produkte (filterErotic greift nicht immer)
    "gleitgel", "lubricant", "intim", "kondome", "vibrator",
    # Modell-/fahrzeugspezifische Teile (z.B. Sonnenblende für Nissan XY)
    "passend für", "kompatibel mit", "ersatzteil", "oem ", "original-",
    "für nissan", "für bmw", "für mercedes", "für vw ", "für volkswagen",
    "für audi", "für ford", "für opel", "für toyota", "für honda",
    "für peugeot", "für renault", "für seat", "für skoda", "für hyundai",
    "für kia", "für fiat", "für volvo", "für mazda", "für suzuki",
    # Deko / Heimtextilien / Handwerk die nichts bringen
    "tapisserie", "wandteppich", "vorhang ", "gardine", "jalousie", "rollo ",
    "doppelrollo", "flächenvorhang",
    "vase ", "glasvase", "blumenvase", "kerzenhalter", "bilderrahmen",
    "häkelnadel", "stricknadel", "häkelset", "wollnadel", "strickgarn",
    "nähgarn", "nähnadel", "stoff ", "fleece ", "filznadel",
    # Medizin / Teststreifen
    "teststreifen", "blutzucker", "blutdruck",
    # US-Importprodukte ohne DE-Relevanz
    "toskanische bronze", "pfister ",
    # Tastaturen/Eingabegeräte mit nicht-DACH-Layout (Amazon trennt das nicht per Kategorie)
    "norwegisches layout", "norwegische tastatur", "norwegisch layout",
    "schwedisches layout", "schwedische tastatur", "schwedisch layout",
    "dänisches layout", "dänische tastatur", "dänisch layout",
    "finnisches layout", "finnische tastatur", "finnisch layout",
    "ukrainisches layout", "ukrainische tastatur", "ukrainisch layout",
    "russisches layout", "russische tastatur", "russisch layout", "kyrillisch",
    "polnisches layout", "polnische tastatur",
    "tschechisches layout", "ungarisches layout", "türkisches layout",
    "griechisches layout", "nordisches layout", "skandinavisches layout",
]

# Pre-compiled Regex-Sets (einmal beim Import, statt pro Produkt zu schleifen).
# Spart CPU auf dem schmalen Render-Server bei 2.400 Produkten/Run.
_EXCLUDE_RE = re.compile("|".join(re.escape(kw) for kw in EXCLUDE_KEYWORDS))
_KEYWORD_RE: dict[str, "re.Pattern"] = {
    cat: re.compile("|".join(re.escape(kw) for kw in kws))
    for cat, kws in KEYWORD_MAP.items()
}


_GAMING_PERIPHERAL_RE = re.compile(
    r'\b(maus|mouse|mauspad|tastatur|keyboard|headset|monitor|'
    r'gaming[-\s]?stuhl|gaming[-\s]?chair)\b'
)


def _reroute_peripheral(cat: str, title_l: str) -> str:
    """Gaming-Peripherie (Maus/Tastatur/Headset/Monitor/Stuhl) gehört zu
    'Computer & Zubehör', damit die Games-Kachel echte Spiele/Konsolen zeigt
    statt fast nur Mäusen. 'controller' bleibt bewusst in Games."""
    if cat == "Games" and _GAMING_PERIPHERAL_RE.search(title_l):
        return "Computer & Zubehör"
    return cat


def classify_category(title: str, root_cat: int = 0) -> str | None:
    """
    Gibt Kategorie zurück oder None wenn das Produkt nicht angezeigt werden soll.
    Reihenfolge: rootCat Exclude → rootCat Map → Keyword-Fallback → ablehnen.
    """
    title_l = title.lower()

    # 1. rootCat-Ausschluss (bekannte Junk-Kategorien wie Fashion, Bücher, Toys)
    if root_cat and root_cat in EXCLUDE_ROOTCATS:
        return None

    # 2. Titel-Ausschluss-Keywords (Sicherheitsnetz für unbekannte rootCats)
    if _EXCLUDE_RE.search(title_l):
        return None

    # 3. rootCat-Mapping (zuverlässig wenn ID bekannt)
    if root_cat and root_cat in ROOTCAT_MAP:
        mapped = ROOTCAT_MAP[root_cat]
        # Kamera & Foto hat bei Keepa keine eigene rootCat-ID (571860 ist nur ein
        # Kind von Elektronik & Foto/562066) — jedes Kamera-Produkt würde sonst
        # immer als "Elektronik & Foto" einsortiert und die Kategorie bliebe
        # für immer leer. Titel-Keywords zuerst prüfen, dann erst den Fallback.
        if mapped == "Elektronik & Foto" and _KEYWORD_RE["Kamera & Foto"].search(title_l):
            return "Kamera & Foto"
        return _reroute_peripheral(mapped, title_l)

    # 4. Keyword-Fallback (exhaustiv — kein Catch-all mehr)
    for cat, pattern in _KEYWORD_RE.items():
        if pattern.search(title_l):
            return _reroute_peripheral(cat, title_l)

    # 5. Kein Match → ablehnen
    return None


# ---------------------------------------------------------------------------
# Stündlicher Preis-Check via Keepa /product (minimal, ~2–3 Tokens/ASIN)
# ---------------------------------------------------------------------------

async def hourly_keepa_price_check():
    """
    Prüft die Preise aktiver Deals via Keepa /product (history=0).

    Gestaffelt (Token-Budget-Schutz bei bis zu 500 aktiven Deals):
      - Top Picks + "Allzeittiefpreis"-Deals + volatile Deals → jede Stunde
      - alle übrigen → nur wenn seit ≥ 3h nicht geprüft
    Preis nicht mehr gut → sofort deaktivieren.
    Volatil (≥3 Preissprünge >3%) + schwacher Rabatt → deaktivieren.
    Preis weiterhin gut → current_price aktualisieren UND last_updated refreshen,
    damit dauerhaft günstige Deals nicht durch die 4h-Ablauffalle fallen.
    """
    print(f"[{datetime.utcnow().isoformat()}] Keepa Preis-Check …")
    db  = await get_pool()
    now = datetime.utcnow()

    async with db.acquire() as conn:
        # Tier-Staffelung: Top 100 (deal_score) stündlich, Rest alle 4h → ~60% Token-Einsparung
        active = await conn.fetch(
            "SELECT asin, name, current_price, avg90_price, avg180_price, all_time_low, "
            "category, rating, reviews, sales_rank FROM products "
            "WHERE is_active=true AND ("
            "  last_checked IS NULL "
            "  OR (deal_score >= (SELECT PERCENTILE_CONT(0.8) WITHIN GROUP (ORDER BY deal_score) "
            "                     FROM products WHERE is_active=true) "
            "      AND last_checked < NOW() - INTERVAL '1 hour') "
            "  OR last_checked < NOW() - INTERVAL '4 hours'"
            ")"
        )

    if not active:
        print("  Keepa Preis-Check: nichts fällig.")
        return

    asins         = [row["asin"] for row in active]
    current_prices = await fetch_current_prices(asins, domain=3)

    if not current_prices:
        print("  Keepa Preis-Check: keine Preisdaten erhalten — Abbruch")
        return

    # Volatilität: Anzahl Preissprünge >3% über die letzten 12 gespeicherten Punkte.
    # Reihenfolge per id (monoton) statt Zeitstempel (price_history.timestamp ist TEXT).
    move_counts = await _count_price_moves(asins)

    deactivated = volatile_cnt = 0
    async with db.acquire() as conn:
        for row in active:
            asin       = row["asin"]
            live_price = current_prices.get(asin)
            if live_price is None:
                continue

            avg90  = row["avg90_price"]  or 0.0
            avg180 = row["avg180_price"] or 0.0
            atl    = row["all_time_low"] or 0.0
            volatile = move_counts.get(asin, 0) >= 3
            if volatile:
                volatile_cnt += 1

            # Volatil UND schwacher Rabatt (kaum unter avg90) → faul, raus.
            weak_volatile = volatile and avg90 > 0 and live_price > avg90 * 0.95

            if weak_volatile or not passes_hard_filters(
                row["rating"], row["reviews"], row["sales_rank"] or 0,
                row["category"], live_price, avg90, atl, avg180,
                title=row["name"] or "",
            ):
                await conn.execute(
                    "UPDATE products SET is_active=false, is_top_pick=false, "
                    "current_price=$2, last_checked=$3 WHERE asin=$1",
                    asin, live_price, now,
                )
                deactivated += 1
            else:
                score, breakdown = calculate_deal_score(
                    live_price, avg90, atl,
                    row["sales_rank"] or 0, row["category"],
                    row["rating"], row["reviews"],
                    price_updated=now,
                )
                tag = determine_tag(live_price, atl, avg90, avg180, atl_confirmed=False)
                # last_updated wird mit-refresht: bestätigt-gute Deals laufen nicht aus,
                # auch wenn Keepa sie nicht mehr als "frischen" Deal im /deal-Stream meldet.
                # is_volatile steuert die Prüf-Frequenz (volatil → stündlich statt 3h).
                # all_time_low mitziehen: fällt der Preis unter das gespeicherte
                # Tief, ist das neue Tief der aktuelle Preis. Verhindert den
                # unmöglichen Zustand "aktueller Preis < Allzeittief" zwischen
                # zwei Deep-Syncs. NULLIF(...,0) fängt den Default 0 ab.
                await conn.execute(
                    "UPDATE products SET current_price=$2, deal_score=$3, tag=$4, "
                    "last_checked=$5, last_updated=$5, score_breakdown=$6, is_volatile=$7, "
                    "all_time_low = LEAST(NULLIF(all_time_low, 0), $2) "
                    "WHERE asin=$1",
                    asin, live_price, score, tag, now, breakdown, volatile,
                )
                await conn.execute(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    asin, live_price, now,
                )

    if deactivated > 0:
        await _promote_backups_simple(deactivated)

    await _recalculate_top_picks()
    print(f"  Keepa Preis-Check fertig: {deactivated} deaktiviert "
          f"({volatile_cnt} volatil), {len(current_prices)} geprüft.")


async def _count_price_moves(asins: list[str], window: int = 12, threshold: float = 0.03) -> dict[str, int]:
    """
    Zählt pro ASIN die Preissprünge > `threshold` über die letzten `window` Punkte.
    Sortiert per id (monoton steigend = chronologisch), unabhängig vom TEXT-Zeitstempel.
    """
    if not asins:
        return {}
    db = await get_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, price FROM ("
            "  SELECT asin, price, id, "
            "         row_number() OVER (PARTITION BY asin ORDER BY id DESC) AS rn "
            "  FROM price_history WHERE asin = ANY($1)"
            ") t WHERE rn <= $2 ORDER BY asin, id ASC",
            asins, window,
        )
    moves: dict[str, int] = {}
    prev: dict[str, float] = {}
    for r in rows:
        a, p = r["asin"], r["price"]
        if a in prev and prev[a] > 0 and abs(p - prev[a]) / prev[a] > threshold:
            moves[a] = moves.get(a, 0) + 1
        prev[a] = p
    return moves


async def _promote_backups_simple(count: int):
    """Rückt die besten Backup-Deals ohne erneute Preis-Verifikation vor."""
    db = await get_pool()
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE products SET is_active=true, is_backup=false "
            "WHERE asin IN ("
            "  SELECT asin FROM products WHERE is_backup=true "
            "  ORDER BY deal_score DESC LIMIT $1"
            ")",
            count,
        )


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
        # ── 1. Keepa /deals (3 Seiten à 150 Kandidaten) ─────────────────────
        # Jede Seite wird sofort gefiltert — nie alle 450 gleichzeitig im RAM
        candidates = []
        skipped_cat = skipped_price = skipped_filter = skipped_score = 0
        got_any = False
        seen_asins: set[str] = set()

        # ── 2. Hard Filters + Scoring (pro Seite, gemeinsam für beide Abfragen) ──
        def process(page_deals):
            nonlocal skipped_cat, skipped_price, skipped_filter, skipped_score
            for d in page_deals:
                if d["asin"] in seen_asins:
                    continue  # Dedup: Elektronik-Zusatzabfrage überschneidet sich mit Hauptabfrage
                if d["current_price"] < MIN_PRICE:
                    skipped_price += 1
                    continue

                cat = classify_category(d["title"] or d["brand"], d.get("root_cat", 0))
                if cat is None:
                    skipped_cat += 1
                    continue
                d["category"] = cat

                cat_min = CATEGORY_MIN_PRICE.get(cat, MIN_PRICE)
                if d["current_price"] < cat_min:
                    skipped_price += 1
                    continue

                if not passes_hard_filters(
                    d["rating"], d["reviews"], d["sales_rank"], cat,
                    d["current_price"], d["avg90"], d["atl"], d["avg180"],
                    title=d["title"] or "",
                ):
                    skipped_filter += 1
                    continue

                score, breakdown = calculate_deal_score(
                    d["current_price"], d["avg90"], d["atl"],
                    d["sales_rank"], cat,
                    d["rating"], d["reviews"],
                    price_updated=None,
                    title=d["title"] or "",
                )
                if score < MIN_SCORE:
                    skipped_score += 1
                    continue

                d["deal_score"]      = score
                d["score_breakdown"] = breakdown
                d["tag"]             = determine_tag(d["current_price"], d["atl"], d["avg90"], d["avg180"], atl_confirmed=False)
                d["original_price"]  = max(d["avg90"] or d["current_price"] * 1.25,
                                           d["current_price"] * 1.10)
                d["avg_price"]       = d["avg90"] or d["current_price"]
                seen_asins.add(d["asin"])
                candidates.append(d)

        # Hauptabfrage: ganze Whitelist, mind. −15 %
        for page in range(DEAL_PAGES):
            page_deals = await fetch_keepa_deals(
                domain=3, delta_pct=15, min_rating=40, min_reviews=50,
                page=page, client=client,
            )
            if not page_deals:
                break
            got_any = True
            process(page_deals)

        # Zusatzabfrage: nur Elektronik/Geräte, schon ab −10 % → holt mehr echte
        # Geräte ins Angebot, die bei −15 % kaum im Deal-Stream auftauchen.
        for page in range(ELECTRONICS_PAGES):
            page_deals = await fetch_keepa_deals(
                domain=3, delta_pct=10, min_rating=40, min_reviews=50,
                page=page, client=client, include_cats=ELECTRONICS_CAT_IDS,
            )
            if not page_deals:
                break
            got_any = True
            process(page_deals)

        if not got_any:
            print("  Keepa /deals lieferte keine Daten — Abbruch.")
            return 0

        # Sortieren nach Score
        candidates.sort(key=lambda x: x["deal_score"], reverse=True)
        active_pool = candidates[:MAX_ACTIVE]
        backup_pool = candidates[MAX_ACTIVE : MAX_ACTIVE + MAX_BACKUP]

        print(
            f"  Gefiltert: {skipped_price} Preis<{MIN_PRICE}€ · "
            f"{skipped_cat} unbekannte Kat · {skipped_filter} HardFilter · {skipped_score} Score"
        )
        print(f"  {len(candidates)} qualifiziert · {len(active_pool)} aktiv · {len(backup_pool)} Backup")

        # ── 3. DB schreiben ──────────────────────────────────────────────────
        db = await get_pool()
        async with db.acquire() as conn:

            await conn.execute("UPDATE products SET is_top_pick=false")

            # Deals > 24h die nicht im aktuellen Run sind → deaktivieren
            new_asins = {p["asin"] for p in active_pool + backup_pool}
            await conn.execute(
                "UPDATE products SET is_active=false, is_backup=false "
                "WHERE last_updated < NOW() - INTERVAL '4 hours' "
                "AND asin != ALL($1::text[])",
                list(new_asins),
            )

            # MAX_ACTIVE in DB erzwingen: überzählige ältere aktive Deals deaktivieren
            await conn.execute(
                "UPDATE products SET is_active=false, is_top_pick=false "
                "WHERE is_active=true AND asin NOT IN ("
                "  SELECT asin FROM products WHERE is_active=true "
                "  ORDER BY deal_score DESC LIMIT $1"
                ")",
                MAX_ACTIVE,
            )

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
                       sales_rank, tag, score_breakdown, first_seen)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                            $16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26)
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
                    f"https://www.amazon.de/dp/{asin}?tag={_affiliate_tag_for(p['category'])}",
                    is_active, is_backup, is_top_pick, p["is_fba"],
                    p["sales_rank"] or 0, p["tag"], p["score_breakdown"], now,
                )

                await conn.execute(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    asin, p["current_price"], now,
                )
                # KEINE simulierte Historie mehr: snagga wirbt mit "geprüfter
                # Preishistorie" — erfundene Punkte wären ein Etikettenschwindel.
                # Echte Historie kommt ausschließlich aus dem Keepa-Deep-Sync.

    print(f"  Fertig: {len(active_pool)} aktiv, {len(backup_pool)} Backup, "
          f"{min(TOP_PICKS_COUNT, len(active_pool))} Top Picks")

    await _post_new_deals_to_telegram()
    return len(active_pool)


async def _post_new_deals_to_telegram():
    """Postet neue Top-Deals (telegram_posted IS NULL, score >= MIN) auf Telegram. Max 3/Run."""
    from telegram import post_deal, MIN_SCORE
    if not MIN_SCORE:
        return
    db = await get_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, name, current_price, original_price, deal_score, tag, category, affiliate_url "
            "FROM products WHERE is_active=true AND telegram_posted IS NULL "
            "AND deal_score >= $1 ORDER BY deal_score DESC LIMIT 3",
            MIN_SCORE,
        )
    for row in rows:
        success = await post_deal(dict(row))
        if success:
            async with db.acquire() as conn:
                await conn.execute(
                    "UPDATE products SET telegram_posted=$1 WHERE asin=$2",
                    datetime.utcnow(), row["asin"],
                )
            await asyncio.sleep(2)  # Telegram: max 1 Msg/Sekunde pro Bot


async def post_next_mastodon_deal():
    """
    Postet GENAU EINEN neuen Top-Deal als Toot. Wird von eigenen, auf feste
    Uhrzeiten gelegten Scheduler-Jobs aufgerufen (siehe scheduler.py) statt
    stündlich mehrfach — die vorherige Taktung (bis zu 3/Std., 24/7, identische
    Hashtags) wurde von mastodon.social automatisiert als Spam eingestuft.
    """
    from mastodon import post_deal as post_deal_mastodon, MIN_SCORE as MASTODON_MIN_SCORE
    if not MASTODON_MIN_SCORE:
        return
    db = await get_pool()
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT asin, name, current_price, original_price, deal_score, tag, category "
            "FROM products WHERE is_active=true AND mastodon_posted IS NULL "
            "AND deal_score >= $1 ORDER BY deal_score DESC LIMIT 1",
            MASTODON_MIN_SCORE,
        )
    if not row:
        return
    success = await post_deal_mastodon(dict(row))
    if success:
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE products SET mastodon_posted=$1 WHERE asin=$2",
                datetime.utcnow(), row["asin"],
            )


async def check_and_send_price_alerts():
    """
    Prüft bestätigte Preisalarme: Ist der aktuelle Preis eines aktiven Produkts
    auf oder unter den Wunschpreis gefallen, wird eine Alarm-Mail verschickt und
    der Alarm als benachrichtigt markiert (notified_at). Nur aktive Produkte —
    damit der verlinkte /deal/{asin} auch wirklich einen Deal zeigt.
    """
    import alerts
    if not alerts.alerts_enabled():
        return
    db = await get_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT a.id, a.asin, a.email, a.target_price, a.token, "
            "       p.name, p.current_price "
            "FROM price_alerts a JOIN products p ON p.asin = a.asin "
            "WHERE a.confirmed = true AND a.notified_at IS NULL "
            "AND p.is_active = true AND p.current_price > 0 "
            "AND p.current_price <= a.target_price"
        )
        for r in rows:
            ok = await alerts.send_alert(
                r["email"], r["asin"], r["name"] or "dein Produkt",
                float(r["current_price"]), float(r["target_price"]), r["token"],
            )
            if ok:
                await conn.execute(
                    "UPDATE price_alerts SET notified_at=now() WHERE id=$1", r["id"]
                )
            await asyncio.sleep(0.3)  # sanftes Rate-Limit gegen Brevo


async def post_next_bluesky_deal():
    """
    Postet GENAU EINEN neuen Top-Deal auf Bluesky. Gleiche zurückhaltende
    Taktung wie Mastodon (feste Uhrzeiten, siehe scheduler.py) — die
    Spam-Sperre auf mastodon.social soll sich nicht wiederholen.
    """
    from bluesky import post_deal as post_deal_bluesky, MIN_SCORE as BLUESKY_MIN_SCORE
    if not BLUESKY_MIN_SCORE:
        return
    db = await get_pool()
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT asin, name, current_price, original_price, deal_score, tag, category "
            "FROM products WHERE is_active=true AND bluesky_posted IS NULL "
            "AND deal_score >= $1 ORDER BY deal_score DESC LIMIT 1",
            BLUESKY_MIN_SCORE,
        )
    if not row:
        return
    success = await post_deal_bluesky(dict(row))
    if success:
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE products SET bluesky_posted=$1 WHERE asin=$2",
                datetime.utcnow(), row["asin"],
            )




async def _recalculate_top_picks():
    """Setzt die Top Picks nach Score — mit Marken-Vielfalt: max. 2 Produkte
    derselben Marke, damit die prominente Startseiten-Reihe nicht von einer Marke
    dominiert wird. Greift, sobald Marken via Deep-Sync gefüllt sind; leere Marken
    zählen nicht mit (dann wie bisher rein nach Score)."""
    db = await get_pool()
    async with db.acquire() as conn:
        await conn.execute("UPDATE products SET is_top_pick=false")
        rows = await conn.fetch(
            "SELECT asin, brand FROM products WHERE is_active=true "
            "ORDER BY deal_score DESC LIMIT $1",
            TOP_PICKS_COUNT * 4,
        )
        picks: list[str] = []
        brand_count: dict[str, int] = {}
        for r in rows:
            if len(picks) >= TOP_PICKS_COUNT:
                break
            b = (r["brand"] or "").strip().lower()
            if b:
                if brand_count.get(b, 0) >= 2:
                    continue
                brand_count[b] = brand_count.get(b, 0) + 1
            picks.append(r["asin"])
        if picks:
            await conn.execute(
                "UPDATE products SET is_top_pick=true WHERE asin = ANY($1)", picks
            )


# ---------------------------------------------------------------------------
# Nächtlicher Deep-Sync (03:00 Uhr) via Keepa /product
# ---------------------------------------------------------------------------

async def nightly_deep_sync():
    """
    Aktualisiert die Top-Deals vollständig via Keepa /product:
    Preishistorie, Sales Rank, Ø-Preise, echter ATL, Rating, Reviews, Bilder.

    Begrenzt auf die Top-DEEPSYNC_LIMIT aktiven Deals nach Score. Bei 500 aktiven
    Deals würde ein voller Deep-Sync (~10 Tokens/ASIN) das Token-Budget sprengen
    (~6.500 Tokens). Die übrigen Deals bleiben mit /deal- + Preis-Check-Daten aktuell;
    nur der echte ATL ("Allzeittiefpreis"-Tag) fehlt ihnen — das ist für die
    niedriger gerankten Deals akzeptabel.
    """
    print(f"[{datetime.utcnow().isoformat()}] Nachtlicher Deep-Sync …")
    db = await get_pool()

    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin, has_real_history, category, name FROM products WHERE is_active=true "
            "ORDER BY deal_score DESC LIMIT $1",
            DEEPSYNC_LIMIT,
        )
    asins = [r["asin"] for r in rows]
    # Kategorie + Titel je ASIN für ein korrekt gewichtetes Re-Scoring (sonst
    # würde der Deep-Sync die Kategorie-Gewichtung/Junk-Abzüge überschreiben).
    meta_by_asin = {r["asin"]: (r["category"] or "Sonstiges", r["name"] or "") for r in rows}
    # History (history=1, teurer) nur für Produkte OHNE echten Chart abrufen; alle
    # übrigen bekommen ein günstiges Preis-/Stats-/Score-Refresh (history=0).
    # Simulierte Alt-Daten gibt es nicht mehr, daher muss vorhandene echte History
    # nicht nächtlich neu gezogen werden.
    new_asins = {r["asin"] for r in rows if not r["has_real_history"]}
    if not asins:
        print("  Keine Deals für Deep-Sync gefunden.")
        return

    print(f"  Deep-Sync für {len(asins)} ASINs ({len(new_asins)} davon mit History-Abruf) …")
    keepa_data = await enrich_with_keepa(asins, domain=3, new_asins=new_asins)
    now        = datetime.utcnow()

    async with db.acquire() as conn:
        for asin, kd in keepa_data.items():
            # Echtes Allzeittief konsistent zur angezeigten Historie: min aus
            # Keepa-ATL, tatsächlicher Preishistorie und aktuellem Preis. Verhindert
            # "ATL > aktueller Preis" und dass ATL/Ø auf denselben Wert kollabieren.
            hist_prices = [pr for pr, _ in (kd.get("history") or []) if pr and pr > 0]
            atl_candidates = [v for v in (kd["all_time_low"], kd["current_price"],
                                          (min(hist_prices) if hist_prices else None)) if v and v > 0]
            kd["all_time_low"] = min(atl_candidates) if atl_candidates else kd["current_price"]

            cat_db, title_db = meta_by_asin.get(asin, ("Sonstiges", ""))
            score, breakdown = calculate_deal_score(
                kd["current_price"], kd["avg90_price"], kd["all_time_low"],
                kd["sales_rank"], cat_db,
                kd["rating"], kd["reviews"],
                price_updated=now,
                title=title_db,
            )
            # Deep-Sync hat echten ATL aus /product → atl_confirmed=True
            tag = determine_tag(kd["current_price"], kd["all_time_low"],
                                kd["avg90_price"], kd["avg180_price"], atl_confirmed=True)

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
                    last_deep_sync  = $15,
                    image_url       = CASE WHEN $16 != '' THEN $16 ELSE image_url END,
                    brand           = CASE WHEN $17 != '' THEN $17 ELSE brand END
                WHERE asin = $1
            """,
                asin,
                kd["current_price"], kd["original_price"], kd["all_time_low"],
                kd["avg_price"], kd["avg90_price"], kd["avg180_price"],
                kd["rating"], kd["reviews"], kd["sales_rank"], kd["is_fba"],
                score, tag, breakdown, now, kd["image_url"], (kd.get("brand") or ""),
            )

            # Echte Preishistorie IMMER frisch setzen: alte (evtl. simulierte)
            # Punkte löschen, echte Keepa-Serie einspielen, has_real_history setzen.
            # Erst ab jetzt wird für dieses Produkt überhaupt ein Chart gezeigt.
            if kd["history"]:
                recent = kd["history"][-365:]
                await conn.execute("DELETE FROM price_history WHERE asin=$1", asin)
                await conn.executemany(
                    "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                    [(asin, pr, ts) for pr, ts in recent],
                )
                await conn.execute(
                    "UPDATE products SET has_real_history=true WHERE asin=$1", asin
                )
                print(f"    ✓ {asin}: {len(recent)} echte Preispunkte (ersetzt)")

    # Deaktiviere Deals mit Score < 40
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE products SET is_active=false, is_top_pick=false "
            "WHERE is_active=true AND deal_score < $1", MIN_SCORE
        )

    await _recalculate_top_picks()
    print(f"  Deep-Sync fertig: {len(keepa_data)} Produkte aktualisiert.")


async def backfill_missing_history(limit: int = 40):
    """
    Holt echte Keepa-Historie für aktive Produkte, die noch keinen Chart haben
    (has_real_history=false) — höchstgerankte zuerst. Läuft stündlich und füllt so
    neu aufgenommene Produkte zeitnah auf, statt bis zum nächtlichen Deep-Sync
    (03:00) zu warten. Das Limit hält den Token-Verbrauch pro Lauf klein.
    """
    db = await get_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT asin FROM products WHERE is_active=true AND has_real_history=false "
            "ORDER BY deal_score DESC LIMIT $1",
            limit,
        )
    asins = [r["asin"] for r in rows]
    if not asins:
        return

    print(f"[{datetime.utcnow().isoformat()}] History-Backfill für {len(asins)} Produkte …")
    keepa_data = await enrich_with_keepa(asins, domain=3, new_asins=set(asins))

    stored = 0
    async with db.acquire() as conn:
        for asin, kd in keepa_data.items():
            if not kd.get("history"):
                continue
            recent = kd["history"][-365:]
            await conn.execute("DELETE FROM price_history WHERE asin=$1", asin)
            await conn.executemany(
                "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                [(asin, pr, ts) for pr, ts in recent],
            )
            # Allzeittief konsistent zur eingespielten History nachziehen (min aus
            # bisherigem ATL und History-Tief; NULLIF fängt den Default 0 ab).
            hist_prices = [pr for pr, _ in recent if pr and pr > 0]
            new_atl = min(hist_prices) if hist_prices else None
            brand   = kd.get("brand") or ""  # Marke gleich mitnehmen (kommt aus /product)
            if new_atl:
                await conn.execute(
                    "UPDATE products SET has_real_history=true, "
                    "all_time_low = LEAST(NULLIF(all_time_low, 0), $2), "
                    "brand = CASE WHEN $3 != '' THEN $3 ELSE brand END WHERE asin=$1",
                    asin, new_atl, brand,
                )
            else:
                await conn.execute(
                    "UPDATE products SET has_real_history=true, "
                    "brand = CASE WHEN $2 != '' THEN $2 ELSE brand END WHERE asin=$1",
                    asin, brand,
                )
            stored += 1
    print(f"  History-Backfill fertig: {stored} Produkte mit neuem Chart.")
