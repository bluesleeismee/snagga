"""
Deal-Scoring, Hard-Filter und Tag-Logik für snagga.de
"""
import math
import json
import os
import re
from datetime import datetime

from sortiment import ist_raus

# ---------------------------------------------------------------------------
# Die eine Rabattregel (David, 15.08.2026)
# ---------------------------------------------------------------------------
# Referenz ist der gewichtete Durchschnitts-Buy-Box-Preis der letzten 90 TAGE,
# die Schwelle liegt 10 % darunter.
#
# Vorher stand hier 20 % — gegen einen Wert, der „avg90" hiess, aber der
# WOCHEN-Durchschnitt war (siehe keepa.py: Keepas /deal-Intervalle sind Tag /
# Woche / Monat / 90 Tage, gelesen wurden sie als Ø30/Ø90/Ø180/Ø365). Gegen den
# Wochenschnitt sind 20 % nichts: jedes Kleinteil mit normalem Preisgezappel
# erfüllt das mehrmals im Monat, ein Monitor dagegen fast nie. Genau deshalb
# bestand die Einlagesohle und der Markenartikel nicht.
#
# 10 % gegen den 90-Tage-Schnitt sind die deutlich HÖHERE Hürde: der Wert ist
# träge und lässt sich durch eine Preisdelle der letzten Tage nicht drücken.
#
# Über Env verstellbar, ohne Deploy. Höher (0.92) = mehr Deals, schwächerer
# Preisvorteil. Niedriger (0.85) = strenger.
QUALITY_DISCOUNT_FACTOR = float(os.getenv("QUALITY_DISCOUNT_FACTOR", "0.90"))

# Zweite Bedingung: die Ersparnis muss auch in Euro spürbar sein.
#
# 10 % sind bei 25 € genau 2,50 € — rechnerisch ein Deal, aber niemand stellt
# dafür den Wecker. Bei 400 € sind dieselben 10 % vierzig Euro. Eine feste
# Euro-Untergrenze hebt die effektive Prozenthürde für billige Ware automatisch
# an (bei 25 € braucht es 32 %, bei 200 € reichen die 10 %) und macht damit elf
# kategorieabhängige Preisgrenzen überflüssig.
QUALITY_MIN_ERSPARNIS_EUR = float(os.getenv("QUALITY_MIN_ERSPARNIS_EUR", "8"))

# Anti-Spike gegen den 30-Tage-Schnitt: Der Preis muss auch unter dem letzten
# Monat liegen, nicht nur unter dem Quartal. Ohne diese Klammer genügt es, dass
# ein Produkt vor zwei Monaten teuer war — der 90-Tage-Schnitt bliebe hoch,
# obwohl der heutige Preis seit Wochen der normale ist. Die 0.97 lassen
# Rundungsrauschen durch, nicht mehr.
ANTI_SPIKE_FAKTOR_30T = float(os.getenv("ANTI_SPIKE_FAKTOR_30T", "0.97"))

# Mindest-Bewertungszahl, wenn Keepa keinen Sales-Rank liefert. Ohne Rang ist die
# Bewertungsbasis der einzige verbleibende Nachfragebeleg — siehe
# hard_filter_reason(). Über Env verstellbar, um die Wirkung zu messen.
RANKLESS_MIN_REVIEWS = int(os.getenv("RANKLESS_MIN_REVIEWS", "500"))

# Die Preisstaffel von 2026-08-12 ist entfallen (David, 15.08.2026).
#
# Sie war der Versuch, eine zu hohe Prozenthürde für teure Ware abzumildern:
# 20 % unter Ø90 gibt es auf Kleinteile ständig, auf einen 400-€-PC fast nie.
# Also wurde nach Preis gestaffelt (10 % ab 300 €, 14 % ab 100 €, sonst 20 %).
#
# Mit der korrigierten Referenz braucht es das nicht mehr. Die alte Hürde war
# nur deshalb so hoch angesetzt, weil sie gegen den WOCHEN-Schnitt gemessen hat
# und dort nichts galt. Gegen den echten 90-Tage-Schnitt sind 10 % für alle
# Preisklassen anspruchsvoll, und die Mindestersparnis in Euro erledigt die
# Kleinteile sauberer als drei Preisstufen. Eine Regel statt vier.

# Verkaufsrang-Aufschlag für hochpreisige Artikel. Der Rang misst Stückzahlen
# innerhalb der Oberkategorie — dort konkurriert ein Laptop mit USB-Kabeln, die
# sich um Größenordnungen häufiger verkaufen. Ein guter Laptop landet damit
# zwangsläufig jenseits der 18.000er-Grenze von „Computer & Zubehör", obwohl
# ihn niemand als Ladenhüter bezeichnen würde. Der Aufschlag korrigiert diesen
# Maßstabsfehler, statt die Grenze für alle zu lockern.
RANK_BONUS_AB_EUR    = float(os.getenv("RANK_BONUS_AB_EUR", "100"))
RANK_BONUS_FAKTOR    = float(os.getenv("RANK_BONUS_FAKTOR", "3.0"))

# Vertrauens-Signal für Produkte ohne bekannte Marke (siehe hard_filter_reason,
# Abschnitt b). Anteil des erlaubten Rangfensters, den ein solches Produkt
# unterbieten muss — 0.5 heisst: bessere Hälfte. Bewertungen sichern nur noch
# Plausibilität, sie ersetzen den Nachfragebeleg nicht mehr.
VERTRAUEN_RANG_ANTEIL = float(os.getenv("VERTRAUEN_RANG_ANTEIL", "0.5"))
VERTRAUEN_MIN_REVIEWS = int(os.getenv("VERTRAUEN_MIN_REVIEWS", "100"))


def erforderlicher_rabatt_faktor(current: float) -> float:
    """
    Faktor gegenüber dem 90-Tage-Ø, den ein Angebot unterschreiten muss.

    Seit 15.08.2026 preisunabhängig — die Staffelung ist entfallen (siehe oben).
    Die Funktion bleibt bestehen, damit Aufrufer und Tests nicht brechen.
    """
    return QUALITY_DISCOUNT_FACTOR

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
    atl:        float = 0,
    avg30:      float = 0,
    title:      str = "",
    brand:      str = "",
    atl_ist_beleg: bool = False,
    sub_category: str = "",
) -> str | None:
    """
    Wie passes_hard_filters(), gibt aber den GRUND der Ablehnung zurück
    (None = bestanden). Existiert, weil "1.652 durch HardFilter aussortiert"
    im Log nicht verrät, welche der acht Bedingungen der Engpass ist — ohne
    diese Aufschlüsselung lässt sich das Deal-Angebot nur blind nachjustieren.

    passes_hard_filters() ist ein dünner Wrapper darum, damit bestehende
    Aufrufer unverändert weiterlaufen.

    Parameter seit 15.08.2026:
      `avg90`  echter 90-Tage-Durchschnitt — die EINZIGE Rabattreferenz.
      `avg30`  30-Tage-Durchschnitt, nur für den Anti-Spike. 0 = unbekannt.
      `atl`    belegtes Allzeittief oder 0. Zählt nur mit `atl_ist_beleg=True`;
               der /deal-Endpoint liefert kein Tief, deshalb ist False Default.
      `sub_category`  für die RAUS-Prüfung. Leer = noch nicht geladen, dann
               wird nicht geprüft (siehe sortiment.ist_raus).
    """
    # Nur Neuware: gebrauchte / generalüberholte / B-Ware sofort aussortieren.
    if is_excluded_condition(title):
        return "zustand"

    # Ausgeschlossene Unterkategorie (sortiment.RAUS). Steht bewusst weit oben:
    # was gar nicht ins Sortiment gehört, muss nicht erst auf Rabatt geprüft
    # werden — und im Log ist "kategorie_raus" die aussagekräftigste Antwort.
    if ist_raus(category, sub_category):
        return "kategorie_raus"

    if rating < 4.0:
        return "rating"

    if reviews < 100:
        return "reviews"

    # Rang-Grenze: ab RANK_BONUS_AB_EUR gelockert, weil der Rang Stückzahlen
    # gegen den Kleinteil-Massenmarkt derselben Oberkategorie misst (siehe
    # Kommentar bei RANK_BONUS_FAKTOR). Ohne diese Korrektur scheitert jedes
    # Kernprodukt an einer Grenze, die für Zubehör kalibriert ist.
    max_rank = CATEGORY_MAX_RANK.get(category, 30_000)
    if current >= RANK_BONUS_AB_EUR:
        max_rank = int(max_rank * RANK_BONUS_FAKTOR)
    if sales_rank > 0 and sales_rank > max_rank:
        return "sales_rank"

    # Fehlender Sales-Rank hiess bisher: Nachfrage-Prüfung entfällt komplett.
    # Gemessen am 11.08.2026 kamen so 17 von 92 aktiven Deals ganz ohne
    # Nachfragebeleg ins Schaufenster, darunter ein Laptop für 4.276 € mit 100
    # Bewertungen. Der Rang fehlt oft aus technischen Gründen und nicht, weil
    # niemand das Produkt kauft — deshalb keine pauschale Ablehnung, sondern der
    # zweite echte Nachfragebeleg: eine solide Bewertungsbasis. (Entscheidung
    # David, 11.08.2026.)
    if sales_rank <= 0 and reviews < RANKLESS_MIN_REVIEWS:
        return "kein_rang_kein_beleg"

    # ── Referenz: 90 Tage, ohne Ausweichmöglichkeit ─────────────────────────
    # Keine 90-Tage-Historie → keine Aussage über den Kaufzeitpunkt und ein
    # leerer Chart. Solche Produkte werden abgelehnt statt notdürftig gegen
    # einen kürzeren Zeitraum geprüft (Entscheidung David, 15.08.2026). Das
    # kostet uns Neuerscheinungen — die sind aber selten echte Deals.
    if avg90 <= 0:
        return "keine_referenz_90t"

    # ── Die Rabattregel: 10 % unter dem 90-Tage-Ø UND mind. 8 € Ersparnis ────
    # Beide Bedingungen zusammen, kein Oder. Der frühere Ausweg „nahe am
    # Allzeittief" ist ersatzlos entfallen: bei der Discovery gab es nie ein
    # belegtes Tief, sondern nur den avg365-Proxy, und über dieses Loch kam
    # praktisch jedes Kleinteil ohne echten Preisvorteil ins Schaufenster.
    ersparnis = avg90 - current
    if current > avg90 * QUALITY_DISCOUNT_FACTOR:
        return "rabatt_zu_klein"
    if ersparnis < QUALITY_MIN_ERSPARNIS_EUR:
        return "ersparnis_zu_klein"

    # ── Anti-Spike gegen den Monat ──────────────────────────────────────────
    # Der Preis muss auch unter dem 30-Tage-Schnitt liegen. Sonst genügt es,
    # dass ein Produkt vor zwei Monaten teuer war: der 90-Tage-Schnitt bliebe
    # hoch, obwohl der heutige Preis längst der normale ist.
    if avg30 > 0 and current > avg30 * ANTI_SPIKE_FAKTOR_30T:
        return "anti_spike_30t"

    # Belegtes Allzeittief ist ab hier nur noch ein PLUS für den Score und den
    # Tag, kein Ersatz für die Rabattregel. `atl`/`atl_ist_beleg` bleiben in der
    # Signatur, damit Aufrufer und Tag-Logik dieselbe Datenquelle benutzen.

    # (b) Vertrauens-Signal: bekannte Marke ODER echter Nachfragebeleg.
    #
    #     Bis 13.08.2026 lautete die Alternative `rating >= 4.3 and reviews >= 500`.
    #     Die Regel wirkte streng, selektierte aber genau falsch herum: eine
    #     Bewertungsmasse von 500+ bei 4.3 Sternen ist für No-Name-Marketplace-
    #     Ware der Normalfall (und zudem käuflich), während ein frisch
    #     eingeführter Monitor eines echten Nischenherstellers sie nie erreicht.
    #     Der Filter hat also zuverlässig viel-bewerteten Ramsch durchgelassen
    #     und neue, hochwertige Ware ausgesperrt.
    #
    #     Ersetzt durch den Verkaufsrang als primären Beleg: er misst tatsächlich
    #     verkaufte Stückzahlen und lässt sich nicht kaufen. Verlangt wird die
    #     bessere Hälfte des ohnehin erlaubten Rangfensters — plus eine
    #     Bewertungsbasis, die nur noch Plausibilität sichern muss (100 statt 500).
    #     Unterm Strich: strenger gegen Bewertungsfarmen, offener für Neuware.
    if not is_known_brand(brand, title):
        rang_fenster = CATEGORY_MAX_RANK.get(category, 30_000)
        if current >= RANK_BONUS_AB_EUR:
            rang_fenster = int(rang_fenster * RANK_BONUS_FAKTOR)
        starker_rang = 0 < sales_rank <= rang_fenster * VERTRAUEN_RANG_ANTEIL
        if not (starker_rang and rating >= 4.2 and reviews >= VERTRAUEN_MIN_REVIEWS):
            return "kein_vertrauenssignal"

    return None


def passes_hard_filters(
    rating:     float,
    reviews:    int,
    sales_rank: int,
    category:   str,
    current:    float,
    avg90:      float,
    atl:        float = 0,
    avg30:      float = 0,
    title:      str = "",
    brand:      str = "",
    atl_ist_beleg: bool = False,
    sub_category: str = "",
) -> bool:
    """Gibt True zurück wenn das Produkt alle Mindestanforderungen erfüllt."""
    return hard_filter_reason(
        rating, reviews, sales_rank, category, current, avg90, atl,
        avg30, title, brand, atl_ist_beleg, sub_category,
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
    # Ohne belegtes Allzeittief wird dessen Gewicht auf den Ø90-Abstand
    # umgelegt statt verschenkt (David, 15.08.2026).
    #
    # Vorher floss bei fehlendem Tief eine harte Null mit 30 % Gewicht ein, das
    # Maximum lag damit bei 70 Punkten. Solange der /deal-Endpoint einen
    # avg365-PROXY als „Tief" lieferte, fiel das nicht auf; seit der Proxy
    # entfernt ist, hätte jeder frisch entdeckte Deal 30 Punkte eingebüsst und
    # wäre reihenweise an MIN_SCORE gescheitert — ein Qualitätsfilter, der in
    # Wahrheit nur misst, ob /product schon gelaufen ist.
    if atl > 0:
        raw = f_avg * 0.40 + f_atl * 0.30 + f_pop * 0.20 + f_stab * 0.10
    else:
        raw = f_avg * 0.70 + f_pop * 0.20 + f_stab * 0.10
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
