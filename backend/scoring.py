"""
Deal-Scoring, Hard-Filter und Tag-Logik für snagga.de
"""
import math
import json
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Bekannte Marken (Quality Gate)
# ---------------------------------------------------------------------------

# Kuratierte, im D-A-CH-Raum bekannte Marken. Alles kleingeschrieben.
# Zweck: Deals bekannter Marken brauchen weniger Review-Beweislast als
# No-Name-Marketplace-Ware (siehe Quality Gate in passes_hard_filters).
KNOWN_BRANDS: frozenset[str] = frozenset({
    # Elektronik / Computer
    "apple", "samsung", "sony", "lg", "panasonic", "philips", "sharp", "toshiba",
    "hisense", "medion", "grundig", "jbl", "bose", "sennheiser", "teufel", "sonos",
    "beats", "jabra", "soundcore", "anker", "ugreen", "belkin", "baseus",
    "logitech", "razer", "corsair", "steelseries", "hyperx", "roccat", "cherry",
    "keychron", "trust", "elgato", "rode", "shure", "blue",
    "asus", "msi", "acer", "lenovo", "hp", "dell", "gigabyte", "asrock",
    "intel", "amd", "nvidia", "crucial", "kingston", "sandisk", "samsung evo",
    "western digital", "wd", "seagate", "verbatim", "transcend", "pny", "lexar",
    "tp-link", "avm", "fritz!", "netgear", "devolo", "d-link", "zyxel",
    "amazon", "kindle", "echo", "ring", "blink", "eufy", "google", "nest",
    "xiaomi", "huawei", "honor", "oneplus", "nothing", "fairphone", "motorola",
    "nokia", "gigaset", "doro", "emporia",
    "garmin", "fitbit", "polar", "suunto", "amazfit", "withings",
    "gopro", "dji", "insta360", "canon", "nikon", "fujifilm", "olympus",
    "om system", "pentax", "sigma", "tamron", "manfrotto", "neewer", "godox",
    "epson", "brother", "kodak", "polaroid", "instax",
    "hama", "varta", "duracell", "energizer", "osram", "ledvance", "paulmann",
    "brennenstuhl", "tfa dostmann", "bresser",
    # Games
    "nintendo", "playstation", "xbox", "sega", "ubisoft", "ea", "activision",
    "rockstar games", "capcom", "bandai namco", "thrustmaster", "8bitdo",
    "turtle beach", "nacon", "hori", "logitech g",
    # Haushalt / Küche
    "bosch", "siemens", "miele", "aeg", "bauknecht", "beko", "gorenje",
    "liebherr", "samsung", "grundig", "braun", "krups", "tefal", "rowenta",
    "moulinex", "wmf", "zwilling", "fissler", "silit", "le creuset", "tchibo",
    "melitta", "severin", "russell hobbs", "delonghi", "de'longhi", "philips",
    "kitchenaid", "kenwood", "smeg", "graef", "ritter", "cloer", "unold",
    "gastroback", "sage", "nespresso", "sodastream", "brita", "emsa", "leifheit",
    "vileda", "kärcher", "karcher", "dyson", "shark", "bissell", "vorwerk",
    "irobot", "roborock", "dreame", "ecovacs", "tineco", "levoit", "ninja",
    "instant pot", "cosori", "duronic", "clatronic", "bomann", "koenic", "trisa",
    # Baumarkt / Garten
    "makita", "dewalt", "einhell", "metabo", "milwaukee", "ryobi", "worx",
    "black+decker", "black + decker", "stanley", "wera", "wiha", "knipex",
    "gedore", "hazet", "proxxon", "dremel", "fein", "festool", "hilti",
    "gardena", "fiskars", "wolf-garten", "husqvarna", "stihl", "al-ko",
    "abus", "burg-wächter", "yale", "nuki", "tesa", "fischer", "3m",
    # Drogerie / Körperpflege
    "oral-b", "philips sonicare", "braun", "gillette", "wilkinson", "remington",
    "babyliss", "ghd", "dyson", "beurer", "medisana", "omron", "nivea",
    "l'oréal", "loreal", "garnier", "schwarzkopf", "wella", "kerastase",
    "kérastase", "olaplex", "cerave", "la roche-posay", "eucerin", "vichy",
    "neutrogena", "bioderma", "weleda", "dove", "axe", "old spice", "colgate",
    "elmex", "meridol", "sensodyne", "listerine", "always", "pampers",
    # Sport / Freizeit / Outdoor
    "adidas", "nike", "puma", "reebok", "asics", "new balance", "under armour",
    "salomon", "merrell", "columbia", "the north face", "jack wolfskin",
    "vaude", "deuter", "tatonka", "mammut", "osprey", "thule", "uvex",
    "alpina", "giro", "shimano", "sram", "topeak", "sks", "busch+müller",
    "sigma sport", "wahoo", "tacx", "elite", "zwift", "decathlon", "kettler",
    "hammer", "schildkröt", "hudora", "intex", "bestway", "coleman", "campingaz",
    "stanley", "esbit", "petzl", "black diamond", "leki", "komperdell",
    "berkley", "shimano fishing", "daiwa", "rapala",
    # Auto / Motorrad
    "bosch automotive", "castrol", "liqui moly", "sonax", "nigrin", "armor all",
    "meguiar's", "osram automotive", "ctek", "noco", "michelin", "continental",
    "goodyear", "hella", "thule", "menabo", "alca",
    # Musikinstrumente
    "yamaha", "casio", "roland", "korg", "fender", "gibson", "epiphone",
    "ibanez", "harley benton", "thomann", "behringer", "focusrite", "presonus",
    "akg", "audio-technica", "beyerdynamic", "numark", "pioneer dj", "denon dj",
    "native instruments", "arturia", "novation",
    # Spielzeug / Sonstiges mit Markenkraft
    "lego", "playmobil", "ravensburger", "kosmos", "schmidt spiele", "haba",
    "mattel", "hasbro", "barbie", "hot wheels", "fisher-price", "vtech",
    "bruder", "siku", "märklin", "carrera", "tamiya", "revell",
    "leuchtturm1917", "moleskine", "lamy", "faber-castell", "staedtler",
    "stabilo", "edding", "samsonite", "eastpak", "fjällräven", "herschel",
    "carhartt", "levi's", "wenger", "victorinox", "zippo", "maglite",
})

# Geräte-Marken, die sehr oft in Zubehör-Titeln von No-Names auftauchen
# ("Hülle für iPhone", "Armband für Apple Watch"). Für diese zählt der
# Titel-Fallback NICHT — nur ein explizites Marken-Feld.
_ACCESSORY_TRAP_BRANDS = frozenset({
    "apple", "samsung", "sony", "xiaomi", "huawei", "google", "amazon",
    "nintendo", "playstation", "xbox", "echo", "kindle", "ring",
})


def is_known_brand(brand: str, title: str = "") -> bool:
    """
    True, wenn das Produkt erkennbar von einer bekannten Marke stammt.

    Primär zählt das Keepa-Marken-Feld. Ist es leer (bei /deal-Daten häufig),
    greift ein vorsichtiger Fallback über den Titel-Anfang (Amazon-Konvention:
    Marke steht vorn) — ausgenommen Geräte-Marken, die typischerweise in
    No-Name-Zubehör-Titeln vorkommen (_ACCESSORY_TRAP_BRANDS).
    """
    b = (brand or "").strip().lower()
    if b in KNOWN_BRANDS:
        return True
    if not b and title:
        words = title.strip().lower().split()
        for n in (2, 1):  # zweiwortige Marken zuerst ("russell hobbs", "jack wolfskin")
            if len(words) >= n:
                cand = " ".join(words[:n])
                if cand in KNOWN_BRANDS and cand not in _ACCESSORY_TRAP_BRANDS:
                    return True
    return False

# ---------------------------------------------------------------------------
# Kategorie-Konfiguration
# ---------------------------------------------------------------------------

CATEGORY_MAX_RANK: dict[str, int] = {
    "Elektronik & Foto":          18_000,
    "Computer & Zubehör":         18_000,
    "Kamera & Foto":              10_000,
    "Games":                       5_000,
    "Baumarkt":                   15_000,
    "Drogerie & Körperpflege":    30_000,
    "Küche, Haushalt & Wohnen":   20_000,
    "Elektro-Großgeräte":         10_000,
    "Sport & Freizeit":           25_000,
    "Musikinstrumente & DJ-Equipment": 15_000,
    "Auto & Motorrad":            10_000,
}

# Moderate Ausrichtung auf Elektronik/hochwertige Geräte: Score-Multiplikator je
# Kategorie. Hebt Elektronik/Computer/Kamera/Games/Großgeräte an und dämpft die
# günstigen Massen-Kategorien (Küche/Baumarkt/Drogerie), ohne sie leerzuräumen.
CATEGORY_SCORE_WEIGHT: dict[str, float] = {
    "Elektronik & Foto":               1.15,
    "Computer & Zubehör":              1.15,
    "Kamera & Foto":                   1.15,
    "Games":                           1.15,
    "Elektro-Großgeräte":              1.15,
    "Küche, Haushalt & Wohnen":        0.90,
    "Baumarkt":                        0.90,
    "Drogerie & Körperpflege":         0.90,
}


# ---------------------------------------------------------------------------
# Specificity Penalty
# ---------------------------------------------------------------------------

def specificity_penalty(title: str) -> int:
    """
    Straft Nischenprodukte durch Score-Abzug statt Hard-Block.
    Ein gutes Universal-Produkt mit leicht spezifischem Titel kommt noch durch.
    """
    t = title.lower()
    p = 0

    if re.search(r'\b(passend für|kompatibel mit|ersatzteil)\b', t):
        p += 40
    if re.search(r'\bfür (nissan|bmw|mercedes|vw|volkswagen|audi|ford|opel|toyota|honda|peugeot|renault|seat|skoda|hyundai|kia|fiat|volvo|mazda|suzuki)\b', t):
        p += 35
    if re.search(r'\b(oem |original-|artikel-nr|art\.nr)\b', t):
        p += 25
    # 2+ vierstellige Nummernblöcke im Titel deuten auf Modellcodes hin
    if len(re.findall(r'\b\d{4,}\b', t)) >= 2:
        p += 20

    # Generische Baumarkt-/Haushalt-Ersatzteile ("Entlüftungsabdeckung" u.ä.) —
    # bewusst OHNE "adapter"/"kit", die auch bei echten Marken-Elektronik-
    # Zubehörteilen (Anker, Apple, Ugreen …) sehr häufig im Titel vorkommen.
    if re.search(r'\b(abdeckplane|abdeckung|organizer|halterung|verlängerung)\b', t):
        p += 18

    # Ramsch/Deko/Verbrauchsware, die zwar rechnerisch gut rabattiert ist, aber
    # nicht ins Sortiment passt (Perücke, Weihnachts-Ornament, Ersatzfilter …).
    # Gezielte Substantive statt breiter Wörter ("filter"/"stück"), damit Marken-
    # produkte (Oral-B-Bürstenköpfe, Webcams, LEVOIT-Geräte) NICHT mitfliegen.
    if re.search(r'\b(perücke|haarteil|ornament|girlande|kerze|aufkleber|serviette|kissenbezug|bilderhaken|ersatzfilter|hepa[-\s]?filter|folie|spiegel|sichtschutz(?:folie)?)\b', t):
        p += 30

    return min(p, 60)


# ---------------------------------------------------------------------------
# Zustands-Filter (nur Neuware)
# ---------------------------------------------------------------------------

# Keywords, die auf gebrauchte / generalüberholte / B-Ware hindeuten.
# Wortgrenzen wo nötig, damit z.B. "Gebrauch"/"Gebrauchsanweisung" NICHT matcht.
# Case-insensitive über re.IGNORECASE.
_EXCLUDED_CONDITION_RE = re.compile(
    r'('
    r'general[-\s]?überholt'   # generalüberholt / general-überholt / general überholt
    r'|refurbished|refurb\b'    # refurbished / refurb
    r'|renewed'
    r'|\bgebraucht(e[rsmn]?)?\b' # gebraucht/gebrauchte/-er/-es/-en/-em; NICHT "Gebrauch"/"Gebrauchsanweisung"
    r'|aufbereitet'
    r'|pre[-\s]?owned'          # pre-owned / pre owned / preowned
    r'|\bb[-/\s]?ware\b'        # b-ware / b/ware / b ware
    r'|\bretoure\b'
    r')',
    re.IGNORECASE,
)


def is_excluded_condition(title: str) -> bool:
    """
    True, wenn der Titel auf gebrauchte / generalüberholte / B-Ware hindeutet.
    snagga listet ausschliesslich Neuware — solche Produkte werden hart gefiltert.
    """
    if not title:
        return False
    return _EXCLUDED_CONDITION_RE.search(title) is not None


# ---------------------------------------------------------------------------
# Hard Filters
# ---------------------------------------------------------------------------

def passes_hard_filters(
    rating:     float,
    reviews:    int,
    sales_rank: int,
    category:   str,
    current:    float,
    avg90:      float,
    atl:        float,
    avg180:     float = 0,
    title:      str = "",
    brand:      str = "",
) -> bool:
    """Gibt True zurück wenn das Produkt alle Mindestanforderungen erfüllt."""
    # Nur Neuware: gebrauchte / generalüberholte / B-Ware sofort aussortieren.
    if is_excluded_condition(title):
        return False

    if rating < 4.0:
        return False

    # Allgemein: mind. 100 Reviews; Auto & Motorrad: 500 (filtert Modell-Nischenteile)
    min_reviews = 500 if category == "Auto & Motorrad" else 100
    if reviews < min_reviews:
        return False

    max_rank = CATEGORY_MAX_RANK.get(category, 30_000)
    if sales_rank > 0 and sales_rank > max_rank:
        return False

    if avg90 <= 0 and avg180 <= 0:
        return False

    # Anti-Spike: current muss unter avg90 UND avg180 liegen
    # Verhindert Fake-Deals durch kurze Preisspikes (normal €30 → spike €60 → zurück €30)
    ref90  = avg90  if avg90  > 0 else None
    ref180 = avg180 if avg180 > 0 else None

    below90  = ref90  is None or current <= ref90  * 0.92
    below180 = ref180 is None or current <= ref180 * 0.92

    if not (below90 and below180):
        return False

    # avg365 als langfristiger Anker (atl aus /deal = avg365):
    # Wenn avg180 deutlich über avg365 liegt, war avg180 durch einen länger andauernden
    # Spike inflated. Dann muss current auch unter avg365 liegen.
    if atl > 0 and avg180 > 0 and atl < avg180 * 0.80:
        if current > atl * 0.95:
            return False

    # ── Quality Gate (2026-07-05): Glaubwürdigkeit vor Menge ────────────────
    # snagga wirbt mit "keine Fake-Rabatte" — das Regal muss den Claim beweisen.
    # (a) Der Rabatt muss substanziell sein: ≥20% unter Ø90 (Fallback Ø180)
    #     ODER nahe am Allzeittief (aus /deal ist atl der avg365-Proxy —
    #     auch das ist ein starkes "historisch günstig"-Signal).
    ref = avg90 if avg90 > 0 else avg180
    real_discount = ref > 0 and current <= ref * 0.80
    near_atl      = atl > 0 and current <= atl * 1.05
    if not (real_discount or near_atl):
        return False

    # (b) Vertrauens-Signal: bekannte Marke ODER sehr solide Review-Basis.
    #     Das Marken-Feld ist bei /deal-Daten oft leer (Backfill läuft) —
    #     Rating + Review-Anzahl ist daher das primäre Signal, Marke der Bonus.
    if not is_known_brand(brand, title) and not (rating >= 4.3 and reviews >= 500):
        return False

    return True


def is_catalog_quality(
    rating:  float,
    reviews: int,
    brand:   str = "",
    title:   str = "",
) -> bool:
    """
    "Gutes Zeug"-Gate für den dauerhaften /preis-Katalog — bewusst OHNE
    Rabatt-Bedingung (anders als passes_hard_filters). Ein Bestseller lohnt
    eine crawlbare Preisseite, auch wenn er gerade zum Normalpreis steht:
    Leute suchen den Produktnamen, nicht "Deal". Entscheidend ist Nachfrage +
    Seriosität, nicht der Tagespreis.

    Kriterien: Neuware (kein Gebraucht/B-Ware), ≥4.0★, ≥100 Reviews UND
    (bekannte Marke ODER ≥4.3★ mit ≥500 Reviews). No-Name mit dünner
    Review-Basis fällt raus → kein Keepa-Token, keine Thin-Content-Seite.
    """
    if is_excluded_condition(title):
        return False
    if rating < 4.0 or reviews < 100:
        return False
    return is_known_brand(brand, title) or (rating >= 4.3 and reviews >= 500)


# ---------------------------------------------------------------------------
# Deal-Score
# ---------------------------------------------------------------------------

def calculate_deal_score(
    current:       float,
    avg90:         float,
    atl:           float,
    sales_rank:    int,
    category:      str,
    rating:        float,
    reviews:       int,
    price_updated: datetime | None = None,
    title:         str = "",
) -> tuple[int, str]:
    """
    Berechnet Deal-Score (0–100) nach der Strategie-Formel:
      40% Abstand zu 90-Tage-Ø
      30% Abstand zum ATL
      20% Popularität (Sales Rank + Rating + Reviews)
      10% Stabilität (kein Kurzzeit-Ausreisser)

    Gibt (score, breakdown_json) zurück.
    """
    # ── Abstand 90-Tage-Ø (40%) ─────────────────────────────────────────────
    if avg90 > 0 and avg90 > current:
        f_avg = min(1.0, (avg90 - current) / avg90)
    else:
        f_avg = 0.0

    # ── Abstand ATL (30%) ───────────────────────────────────────────────────
    if atl > 0 and avg90 > 0:
        if current <= atl:
            f_atl = 1.0
        else:
            spread = avg90 - atl
            f_atl = 1.0 - ((current - atl) / spread) if spread > 0 else 0.0
    elif atl > 0 and current <= atl:
        f_atl = 1.0
    else:
        f_atl = 0.0
    f_atl = max(0.0, min(1.0, f_atl))

    # ── Popularität (20%) ───────────────────────────────────────────────────
    max_rank = CATEGORY_MAX_RANK.get(category, 30_000)
    if sales_rank > 0 and sales_rank <= max_rank:
        # Invertiert und normiert: niedriger Rank → hoher Faktor
        rank_f = 1.0 - (sales_rank / max_rank)
    elif sales_rank == 0:
        rank_f = 0.5  # unbekannt → neutral
    else:
        rank_f = 0.0

    rating_f = min(1.0, max(0.0, (rating - 4.0) / 1.0)) if rating >= 4.0 else 0.0
    review_f = min(1.0, math.log10(max(1, reviews)) / math.log10(10_000)) if reviews > 0 else 0.0

    f_pop = rank_f * 0.5 + rating_f * 0.3 + review_f * 0.2

    # ── Stabilität (10%) ────────────────────────────────────────────────────
    if price_updated:
        hours = (datetime.utcnow() - price_updated).total_seconds() / 3600
        f_stab = 1.0 if hours >= 24 else 0.3
    else:
        f_stab = 0.5

    # ── Gesamt ──────────────────────────────────────────────────────────────
    raw = f_avg * 0.40 + f_atl * 0.30 + f_pop * 0.20 + f_stab * 0.10
    base_score = max(0, min(100, int(raw * 100)))

    penalty = specificity_penalty(title) if title else 0
    score   = max(0, base_score - penalty)

    # Kategorie-Gewichtung (moderate Elektronik-/Premium-Ausrichtung).
    weight = CATEGORY_SCORE_WEIGHT.get(category, 1.0)
    score  = max(0, min(100, int(round(score * weight))))

    breakdown = json.dumps({
        "avg90":   round(f_avg, 3),
        "atl":     round(f_atl, 3),
        "pop":     round(f_pop, 3),
        "stab":    round(f_stab, 3),
        "rank":    round(rank_f, 3),
        "penalty": penalty,
        "weight":  weight,
    })
    return score, breakdown


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def best_price_since_months(history: list, current: float) -> int | None:
    """
    Wie viele Monate liegt der letzte Zeitpunkt zurück, an dem das Produkt
    genauso günstig oder günstiger war als jetzt (2% Toleranz)?

    history: chronologische Liste [(preis_eur, datetime), …] ECHTER Keepa-Punkte.
    Die aktuelle Niedrigpreis-Phase am Ende der History zählt nicht mit —
    sie IST der Deal. War der Preis davor nie so tief, zählt die volle
    History-Spanne ("Bester Preis seit Aufzeichnungsbeginn").

    None, wenn keine belastbare Aussage möglich ist (zu wenig History, oder
    der Preis war praktisch durchgehend so günstig → kein echtes Urteil).
    """
    if not history or len(history) < 3 or not current or current <= 0:
        return None
    tol = current * 1.02
    now = datetime.utcnow()

    # Trailing-Tief überspringen (die laufende Deal-Phase)
    i = len(history) - 1
    while i >= 0 and history[i][0] <= tol:
        i -= 1
    if i < 0:
        return None  # war im gesamten Fenster nie teurer → kein Urteil

    # Von dort rückwärts: letzter Punkt, der schon einmal ≤ tol war
    j = i
    while j >= 0 and history[j][0] > tol:
        j -= 1
    anchor = history[j][1] if j >= 0 else history[0][1]

    months = (now - anchor).days // 30
    return int(months) if months >= 1 else None


def determine_tag(
    current: float,
    atl: float,        # Echter ATL (nur aus /product Deep-Sync, sonst 0)
    avg90:  float,
    avg180: float,
    atl_confirmed: bool = False,   # True nur wenn ATL aus /product stammt
    months_since_lower: int | None = None,  # aus best_price_since_months()
) -> str:
    """
    Gibt den höchstpriorisierten Tag zurück (maximal einer pro Deal).

    "Allzeittiefpreis" wird NUR vergeben wenn der echte ATL bekannt ist
    (atl_confirmed=True, kommt aus /product Deep-Sync).
    Aus /deal-Daten steht nur avg365 als Proxy — das reicht NICHT für den Tag.

    Seit dem Quality Gate (2026-07-05) kommt praktisch jeder aktive Deal
    ≥20% unter Ø90 ODER nahe ans (Proxy-)Tief — der Fallback am Ende stellt
    sicher, dass JEDE Kachel ein Preishistorie-Urteil trägt.
    """
    # avg90 || avg180 als bester verfügbarer Referenzpreis
    ref = avg90 or avg180

    # Echter ATL nur wenn durch Deep-Sync bestätigt
    if atl_confirmed and atl > 0 and current <= atl * 1.03:
        return "Allzeittiefpreis"

    # Konkretes Urteil aus echter Preishistorie — stärkstes Kaufargument
    if months_since_lower is not None and months_since_lower >= 12:
        return "Bester Preis seit über 1 Jahr"
    if months_since_lower is not None and months_since_lower >= 3:
        return f"Bester Preis seit {months_since_lower} Monaten"

    # Deutlich unter 6-Monats-Durchschnitt
    if avg180 > 0 and current <= avg180 * 0.80:
        return "Historisch günstig"

    # Nahe am Tief (unbestätigt = avg365-Proxy aus /deal)
    if atl > 0 and current <= atl * 1.05:
        return "Historisch günstig"

    # Deutlich unter Referenzpreis
    if ref > 0 and current <= ref * 0.70:
        return "Stark gefallen"

    # Moderat unter Referenzpreis (inkl. Fallback avg180 wenn avg90 fehlt)
    if ref > 0 and current <= ref * 0.85:
        return "Preis gefallen"

    # Fallback: Quality Gate garantiert einen echten Preisrückgang —
    # keine Kachel ohne Urteil.
    if ref > 0 and current < ref:
        return "Preis gefallen"

    return ""
