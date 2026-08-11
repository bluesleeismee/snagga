"""
Deal-Scoring, Hard-Filter und Tag-Logik für snagga.de
"""
import math
import json
import os
import re
from datetime import datetime

# Quality Gate (a): Wie weit muss der Preis unter dem Ø90 liegen, damit ein
# Angebot ins Regal darf? 0.80 = mindestens 20 % darunter.
#
# Über Env verstellbar, weil das der wirksamste Regler für die ANGEBOTSMENGE ist:
# Keepa liefert nur Kandidaten ab −15 % gegenüber der eigenen Referenz, dieses
# Gate verlangt danach nochmals −20 % gegenüber Ø90 — die Kombination ist streng.
# Zum Nachjustieren KEIN Deploy nötig, nur die Env-Variable in Render ändern.
# Höher (z. B. 0.85) = mehr Deals, schwächerer Preisvorteil. Niedriger = strenger.
QUALITY_DISCOUNT_FACTOR = float(os.getenv("QUALITY_DISCOUNT_FACTOR", "0.80"))

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

def hard_filter_reason(
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
) -> str | None:
    """
    Wie passes_hard_filters(), gibt aber den GRUND der Ablehnung zurück
    (None = bestanden). Existiert, weil "1.652 durch HardFilter aussortiert"
    im Log nicht verrät, welche der acht Bedingungen der Engpass ist — ohne
    diese Aufschlüsselung lässt sich das Deal-Angebot nur blind nachjustieren.

    passes_hard_filters() ist ein dünner Wrapper darum, damit bestehende
    Aufrufer unverändert weiterlaufen.
    """
    # Nur Neuware: gebrauchte / generalüberholte / B-Ware sofort aussortieren.
    if is_excluded_condition(title):
        return "zustand"

    if rating < 4.0:
        return "rating"

    # Allgemein: mind. 100 Reviews; Auto & Motorrad: 500 (filtert Modell-Nischenteile)
    min_reviews = 500 if category == "Auto & Motorrad" else 100
    if reviews < min_reviews:
        return "reviews"

    max_rank = CATEGORY_MAX_RANK.get(category, 30_000)
    if sales_rank > 0 and sales_rank > max_rank:
        return "sales_rank"

    if avg90 <= 0 and avg180 <= 0:
        return "keine_referenz"

    # Anti-Spike: current muss unter avg90 UND avg180 liegen
    # Verhindert Fake-Deals durch kurze Preisspikes (normal €30 → spike €60 → zurück €30)
    ref90  = avg90  if avg90  > 0 else None
    ref180 = avg180 if avg180 > 0 else None

    below90  = ref90  is None or current <= ref90  * 0.92
    below180 = ref180 is None or current <= ref180 * 0.92

    if not (below90 and below180):
        return "anti_spike"

    # avg365 als langfristiger Anker (atl aus /deal = avg365):
    # Wenn avg180 deutlich über avg365 liegt, war avg180 durch einen länger andauernden
    # Spike inflated. Dann muss current auch unter avg365 liegen.
    if atl > 0 and avg180 > 0 and atl < avg180 * 0.80:
        if current > atl * 0.95:
            return "avg365_anker"

    # ── Quality Gate (2026-07-05): Glaubwürdigkeit vor Menge ────────────────
    # snagga verspricht, dass jeder gezeigte Preis gegen die echte Historie
    # geprüft ist — das Regal muss diesen Anspruch einlösen.
    # (a) Der Preisvorteil muss substanziell sein: ≥20% unter Ø90 (Fallback Ø180)
    #     ODER nahe am Allzeittief (aus /deal ist atl der avg365-Proxy —
    #     auch das ist ein starkes "historisch günstig"-Signal).
    ref = avg90 if avg90 > 0 else avg180
    real_discount = ref > 0 and current <= ref * QUALITY_DISCOUNT_FACTOR
    near_atl      = atl > 0 and current <= atl * 1.05
    if not (real_discount or near_atl):
        return "rabatt_zu_klein"

    # (b) Vertrauens-Signal: bekannte Marke ODER sehr solide Review-Basis.
    #     Das Marken-Feld ist bei /deal-Daten oft leer (Backfill läuft) —
    #     Rating + Review-Anzahl ist daher das primäre Signal, Marke der Bonus.
    if not is_known_brand(brand, title) and not (rating >= 4.3 and reviews >= 500):
        return "kein_vertrauenssignal"

    return None


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
    return hard_filter_reason(
        rating, reviews, sales_rank, category, current, avg90, atl,
        avg180, title, brand,
    ) is None


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
# Allzeittief — EINE kanonische Quelle für Tag, Kauf-Urteil und Anzeige
# ---------------------------------------------------------------------------

# Toleranz für die ABSOLUTE Aussage "Allzeittiefpreis": keine. Der Claim steht
# direkt neben dem Chart und neben der ausgewiesenen Zahl "Allzeittief" — jeder
# Cent Abstand ist für den Kunden sichtbar als Widerspruch. Historie: die
# Toleranz stand auf 1.03, wodurch ein Preis 3 % ÜBER dem Tief als Allzeittief
# beworben wurde (30,56 € bei Tief 22,59 €, weil zusätzlich ein Proxy-ATL
# durchrutschte — siehe resolve_atl).
ATL_TOL = 1.0

# Wie viele echte Historienpunkte nötig sind, damit das Minimum der gespeicherten
# Preishistorie als belastbares Tief gilt. Ein einzelner Punkt ist immer der
# gerade eingefügte aktuelle Preis — der würde sich selbst zum Allzeittief erklären.
ATL_MIN_HISTORY_POINTS = 3


def resolve_atl(
    current:        float,
    keepa_atl:      float = 0.0,   # stats.atl aus /product (0 = nicht vorhanden)
    stored_atl:     float = 0.0,   # products.all_time_low
    stored_confirmed: bool = False,  # products.atl_confirmed
    history_prices: list | None = None,  # Preise der gespeicherten/frischen Historie
) -> tuple[float, bool]:
    """
    Löst das Allzeittief aus allen verfügbaren Quellen auf und sagt, ob es
    BELEGT ist. Rückgabe: (atl, confirmed).

    Warum diese Funktion existiert — die drei Fehlerquellen, die "Allzeittief"
    dreimal falsch gemacht haben, alle mit derselben Wurzel: es gab keine
    einzige Quelle der Wahrheit.

      1. Der /deal-Endpoint liefert KEIN Allzeittief. Er liefert den 365-Tage-
         Durchschnitt, der als „ATL-Proxy" in dieselbe Spalte `all_time_low`
         geschrieben wurde — ununterscheidbar vom echten Tief. Beim HDMI-Kabel
         war dieser Proxy 30,43 € (= Ø Gesamt) bei echtem Tief 22,59 €.
      2. Der stündliche Preis-Check las diese Spalte und übergab sie mit
         `atl_confirmed=True` an determine_tag — der Proxy wurde also zum
         „bestätigten" Tief gewaschen: 30,56 € ≤ 30,43 € × 1,03 → Allzeittiefpreis.
      3. Überall wurde `min(…, current_price)` gerechnet bzw. `or current_price`
         als Fallback benutzt. Damit ist das „Tief" per Konstruktion NIE über dem
         aktuellen Preis — die Prüfung `current <= atl` kann dann gar nicht mehr
         fehlschlagen. Ein fehlendes Tief wurde so zum garantierten Allzeittief.

    Regeln hier, ausnahmslos:
      * Der AKTUELLE Preis ist niemals Beleg für ein Tief. Er wird nicht in die
        Kandidatenliste aufgenommen — sonst beweist sich der Claim selbst.
      * Ein Proxy (avg365 aus /deal) ist niemals Beleg. `stored_atl` zählt nur,
        wenn es einmal als belegt markiert wurde (`stored_confirmed`).
      * Belege sind: Keepas stats.atl aus /product und das Minimum einer echten
        Preishistorie mit mindestens ATL_MIN_HISTORY_POINTS Punkten.
      * Ohne Beleg → (0.0, False). Kein Rückfall auf irgendeinen Ersatzwert.
    """
    evidence: list[float] = []
    if keepa_atl and keepa_atl > 0:
        evidence.append(float(keepa_atl))
    if stored_confirmed and stored_atl and stored_atl > 0:
        evidence.append(float(stored_atl))
    hp = [float(p) for p in (history_prices or []) if p and p > 0]
    if len(hp) >= ATL_MIN_HISTORY_POINTS:
        evidence.append(min(hp))

    if not evidence:
        return 0.0, False
    return round(min(evidence), 2), True


def atl_for_display(atl: float, current: float) -> float:
    """
    Anzeigewert für „Allzeittief". Ein Tief kann logisch nie über dem aktuellen
    Preis liegen (Keepas Stats laufen einem frischen Tief nach) → nach unten
    klemmen. NUR für die Anzeige — die Tag-/Urteilslogik rechnet mit dem
    unbeschnittenen `atl` aus resolve_atl(), damit der Claim nicht durch das
    Klemmen selbst wahr wird.
    """
    if atl and atl > 0:
        return round(min(atl, current), 2) if current and current > 0 else atl
    return round(current, 2) if current and current > 0 else 0.0


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def best_price_since_months(history: list, current: float) -> int | None:
    """
    Wie viele Monate liegt der letzte Zeitpunkt zurück, an dem das Produkt
    (auch nur geringfügig) günstiger war als jetzt?

    history: chronologische Liste [(preis_eur, datetime), …] ECHTER Keepa-Punkte.
    Harte Regel: die Aussage "Bester Preis seit N Monaten" steht direkt neben
    dem Chart, das dieselbe History zeigt. Es darf im behaupteten Zeitraum
    KEIN einziger tieferer oder gleich hoher Punkt existieren — auch kein
    kurzer Ausreißer (z.B. ein Ein-Tages-Blitzangebot) und auch keine nur
    geringfügig tiefere Preisspitze —, sonst sieht der Kunde im selben Chart
    einen Preis, der die Behauptung widerlegt. Die Toleranz ist deshalb NUR
    für Rundungsrauschen gedacht (Keepa liefert Cent-Werte), nicht um echte,
    aber kleine Preisvorteile zu ignorieren. Deshalb wird rückwärts ab jetzt
    nach dem JÜNGSTEN Punkt gesucht, der (über Rundungsrauschen hinaus)
    billiger war; alles danach (also der beanspruchte Zeitraum) muss
    lückenlos bei oder über dem aktuellen Preis liegen. War der Preis
    nirgends in der History billiger, zählt die volle History-Spanne
    ("Bester Preis seit Aufzeichnungsbeginn").

    None, wenn keine belastbare Aussage möglich ist (zu wenig History, oder
    der jüngste billigere Punkt liegt selbst erst wenige Wochen zurück).
    """
    if not history or len(history) < 3 or not current or current <= 0:
        return None
    # Ein früherer Punkt bricht den Claim, sobald er NICHT spürbar teurer als jetzt
    # war — also auch bei PREISGLEICHHEIT, nicht nur wenn er billiger war (Docstring:
    # kein tieferer ODER gleich hoher Punkt). Vorher testete die Schleife strikt
    # `price < current*0.997`, also nur ~0.3 % billigere Punkte; ein Produkt, das
    # immer wieder exakt denselben Aktionspreis erreicht (z.B. B0BGRDMRPR: 29,91 €
    # mehrfach in den letzten 90 Tagen), fand so KEINEN früheren Punkt und behauptete
    # "Bester Preis seit über 1 Jahr", obwohl derselbe Preis erst vor Wochen im
    # daneben gerenderten Chart sichtbar galt. Toleranz jetzt nach oben: ein Punkt bis
    # 0.3 % über dem aktuellen Preis zählt als „gleich günstig" (nur Rundungsrauschen).
    tol = current * 1.003
    now = datetime.utcnow()

    # Die aktuelle Tief-Strecke bis heute überspringen (sonst ankert der jüngste,
    # zum aktuellen Preis gehörende Punkt sofort auf „jetzt"): erst zurückgehen, bis
    # der Preis einmal spürbar ÜBER dem aktuellen lag, und dann den jüngsten Punkt
    # suchen, der wieder gleich günstig oder günstiger war — das ist der ehrliche
    # „seit"-Zeitpunkt.
    #
    # ACHTUNG (Bug gefunden 2026-08-11 an B06XC43BF6): dieses Überspringen darf
    # NUR preisgleiche Punkte schlucken. Vorher verschlang es auch echte, tiefere
    # Punkte — beim Kühlschrank lag der Preis wenige Tage zuvor bei 184,99 € und
    # 187,00 €, aktuell bei 199,90 €; beide wurden übersprungen, weil noch kein
    # höherer Punkt gesehen war, und die Seite behauptete „Bester Preis seit 8
    # Monaten" direkt neben einem Chart, in dem der tiefere Preis zu sehen war.
    # Ein spürbar tieferer Punkt in dieser Anfangsstrecke bedeutet: der aktuelle
    # Preis ist nicht der beste, es gibt keine ehrliche „seit"-Aussage → None.
    lower_tol = current * 0.997
    anchor = history[0][1]  # Fallback: davor nie so günstig -> ganze Spanne
    seen_higher = False
    for price, ts in reversed(history):
        if not seen_higher:
            if price < lower_tol:
                return None
            if price > tol:
                seen_higher = True
            continue
        if price <= tol:
            anchor = ts
            break

    # Preis war nie spürbar über dem aktuellen (flache Linie / aktuell teuerster
    # Stand) → keine belastbare „Bester Preis seit"-Aussage möglich.
    if not seen_higher:
        return None

    months = (now - anchor).days // 30
    return int(months) if months >= 1 else None


def determine_tag(
    current: float,
    atl: float,        # BELEGTES Allzeittief aus resolve_atl(), sonst 0
    avg90:  float,
    avg180: float,
    atl_confirmed: bool = False,   # zweiter Rückgabewert von resolve_atl()
    months_since_lower: int | None = None,  # aus best_price_since_months()
) -> str:
    """
    Gibt den höchstpriorisierten Tag zurück (maximal einer pro Deal).

    `atl`/`atl_confirmed` MÜSSEN aus resolve_atl() kommen. Jeder Aufrufer, der
    `atl_confirmed=True` von Hand setzt oder einen Wert übergibt, in den der
    aktuelle Preis oder der avg365-Proxy aus /deal eingeflossen ist, erzeugt
    genau den Bug, für den resolve_atl() geschrieben wurde: einen
    „Allzeittiefpreis"-Badge neben einem Chart, der ihn widerlegt.

    Seit dem Quality Gate (2026-07-05) kommt praktisch jeder aktive Deal
    ≥20% unter Ø90 — der Fallback am Ende stellt sicher, dass JEDE Kachel ein
    Preishistorie-Urteil trägt, auch ohne belegtes Tief.
    """
    # avg90 || avg180 als bester verfügbarer Referenzpreis
    ref = avg90 or avg180

    # Absoluter Claim → nur gegen ein belegtes Tief und ohne Toleranz.
    if atl_confirmed and atl > 0 and current <= atl * ATL_TOL:
        return "Allzeittiefpreis"

    # Konkretes Urteil aus echter Preishistorie — stärkstes Kaufargument
    if months_since_lower is not None and months_since_lower >= 12:
        return "Bester Preis seit über 1 Jahr"
    if months_since_lower is not None and months_since_lower >= 3:
        return f"Bester Preis seit {months_since_lower} Monaten"

    # Deutlich unter 6-Monats-Durchschnitt
    if avg180 > 0 and current <= avg180 * 0.80:
        return "Historisch günstig"

    # Nahe am belegten Tief. Früher lief dieser Zweig auch auf den avg365-Proxy
    # aus /deal — „Historisch günstig", weil der Preis nahe am JAHRESDURCHSCHNITT
    # lag, also bei völlig durchschnittlichem Preis. Nur noch mit belegtem Tief.
    if atl_confirmed and atl > 0 and current <= atl * 1.05:
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
