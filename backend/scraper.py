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
from typing import Optional
from datetime import datetime, timedelta

from database import get_pool
from keepa import (
    fetch_keepa_deals, enrich_with_keepa, fetch_keepa_bestsellers,
    fetch_keepa_category_children_named,
)
from scoring import (
    CATEGORY_MAX_RANK,
    passes_hard_filters,
    hard_filter_reason,
    is_catalog_quality,
    calculate_deal_score,
    determine_tag,
    best_price_since_months,
    resolve_atl,
    historien_spanne_tage,
    atl_for_display,
)
from sortiment import kern_namen, KATEGORIEN

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
# Karenzzeit, bis ein Deal ohne echte Preishistorie aus der Liste fliegt. Der
# stündliche Preis-Check versucht in dieser Zeit mehrfach, Historie zu holen —
# klappt es nicht, kann der Deal das Chart-Versprechen nicht einlösen.
CHART_GRACE_HOURS = int(os.getenv("CHART_GRACE_HOURS", "3"))
# Karenzzeit, bis ein aktiver Deal ohne frische Bestätigung aus der Liste fliegt.
#
# „Bestätigt" heisst: entweder hat der Preis-Check ihn erneut gegen die
# Hard-Filter geprüft, oder die Discovery hat ihn erneut gefunden — beide
# schreiben `last_updated`. Passiert keins von beidem, weiss niemand mehr, ob
# der beworbene Preis noch gilt.
#
# 8 Stunden, nicht kürzer: die untere Tier-Stufe des Preis-Checks wird nur alle
# 4 Stunden fällig, der Job läuft stündlich — ein gesunder Deal kann also legitim
# gut 5 Stunden alt sein. 8 lässt Luft für einen ausgefallenen Lauf, ohne dass
# eine Karteileiche einen ganzen Tag stehen bleibt.
PREIS_GRACE_HOURS = int(os.getenv("PREIS_GRACE_HOURS", "8"))
MAX_BACKUP      = 150
TOP_PICKS_COUNT = 10
# Punkte-Untergrenze bei der Entdeckung (David, 16.08.2026: 30 → 18, per Env).
#
# Die 30 stammen aus der Zeit, als der avg365-Proxy als Allzeittief galt: weil
# überall `min(…, current_price)` gerechnet wurde, war `f_atl` praktisch immer
# 1.0 — jeder Kandidat bekam 30 Punkte geschenkt. Seit der Proxy weg ist, liefert
# die Discovery `atl=0`; die Umlage auf `f_avg` gibt bei realistischen 10–25 %
# Rabatt nur 3–8 Punkte zurück. Netto verlor jeder Kandidat rund 25 Punkte,
# während die Schwelle stehen blieb.
#
# Wirkung, gemessen am 16.08.2026: übrig blieben 18 aktive Deals, ihre Scores
# drängten sich bei 30/31. Der Score war damit die eigentliche Rabatthürde und
# verlangte je nach Rang 15–28 % — der AOC-Monitor mit 10,3 % unter Ø90 kam auf
# 27 Punkte und wäre abgelehnt worden. Weil nur hoher PROZENTrabatt durchkam,
# überlebte ausgerechnet billige Massenware (Bettdecke, Teppich, Matratze) —
# das Gegenteil des Umbauziels.
#
# Die Qualitätsprüfung leistet der Hard-Filter (Rabattregel, Mindestersparnis,
# Anti-Spike, Rang, Vertrauenssignal). Der Score sortiert danach die Reihenfolge;
# er soll nicht heimlich ein zweites, strengeres Rabattkriterium sein. 18 lässt
# die Rangfolge intakt und schneidet nur ab, was auch im Filter grenzwertig ist.
MIN_SCORE       = int(os.getenv("MIN_SCORE", "18"))
# Ein Mindestpreis für alle Kategorien (David, 15.08.2026, Stufe 2).
#
# Vorher: 20 € global plus elf kategorieabhängige Werte zwischen 25 und 50 €
# (CATEGORY_MIN_PRICE, siehe unten). Diese Staffel war ein Notbehelf — ein
# Preisschwellwert als Ersatz dafür, dass Kleinteile nicht anders erkennbar
# waren. Genau diese Aufgabe erledigt jetzt die RAUS-Rolle in sortiment.py, und
# zwar treffsicher: ein 22-€-Artikel fliegt raus, weil er aus „Sportmedizin"
# kommt, nicht weil er 22 € kostet.
#
# Was der Preis weiter leisten muss, erledigt QUALITY_MIN_ERSPARNIS_EUR (8 €)
# in scoring.py: die Ersparnis muss spürbar sein. Das hebt die effektive
# Prozenthürde für billige Ware automatisch an (bei 25 € braucht es 32 %,
# bei 200 € reichen die 10 %) — ohne elf Sonderfälle.
MIN_PRICE       = 25.0
DEAL_PAGES      = 16    # Breitensuche: 16 × 150 = 2.400 Kandidaten/Run
# Eine Rabattschwelle für alle Abfragen (David, 15.08.2026). Vorher standen hier
# vier verschiedene Werte (15 / 10 / 10 / 8 %) — nicht aus einem Konzept heraus,
# sondern weil jede neue Abfrage die vorige reparieren sollte. Gemessen wird
# jetzt überall gegen den 90-Tage-Ø (keepa.dateRange=3), und dort ist eine
# einheitliche Schwelle auch verteidigbar.
DEAL_DELTA_PCT  = int(os.getenv("DEAL_DELTA_PCT", "10"))

# ── Kern-Knoten-Abfrage — die Hauptquelle ──────────────────────────────────
# Keepa sortiert den /deal-Stream nach Rabatt-PROZENT. Eine Abfrage über
# Root-Knoten holt damit die Artikel mit dem prozentual tiefsten Sturz, und das
# sind fast ausnahmslos Kleinteile: auf Kabel, Hüllen und Gewürzgläser gibt es
# ständig −40 %, auf einen 400-€-PC fast nie. Hochwertige Ware kam so gar nicht
# erst in den Kandidatentopf — jede Nachjustierung an Filtern und Quoten konnte
# danach nur noch aussortieren, was ohnehin schon Zubehör war.
#
# Zwei Anläufe dagegen sind gescheitert und wurden am 15.08.2026 entfernt:
#   * Eine Hochpreis-Abfrage ab 100 € (12.08.). Richtiger Gedanke, zu grobes
#     Werkzeug — „teuer" ist nicht „Kernprodukt". Über 100 € liegen auch
#     Werkzeugkoffer-Sets und Bandagen (daher der „Leistenbruchgürtel"),
#     während ein 89-€-Monitor durch das Fenster fällt.
#   * Eine Elektronik-Zusatzabfrage mit gelockerter Schwelle (−10 % statt −15 %).
#     Sie holte dieselben Root-Knoten nur noch einmal.
#
# Was wirkt, ist die Steuerung über die KATEGORIE: `includeCategories` bekommt
# die Keepa-Unterknoten, die in sortiment.KATEGORIEN auf KERN stehen (Monitore,
# Laptops, Elektrische Küchengeräte, Elektro- & Handwerkzeuge …). Dann besteht
# das Fenster von vornherein aus der gewünschten Ware, und die Rabatt-Sortierung
# darin wird vom Problem zum Vorteil.
#
# Diese Abfrage existierte seit 13.08. schon — sie lief nur nie, weil
# _kern_knoten() auf der falschen Baumebene suchte (siehe dort).
KERN_PAGES      = int(os.getenv("KERN_PAGES", "10"))
KERN_DELTA_PCT  = int(os.getenv("KERN_DELTA_PCT", "10"))
# Keepa nimmt lange includeCategories-Listen an, aber die URL wächst mit. In
# Häppchen abfragen hält die Requests klein und verteilt das Ergebnis über
# mehrere Kategorien, statt eine einzige das Fenster füllen zu lassen.
KERN_BATCH      = int(os.getenv("KERN_BATCH", "12"))
KERN_AKTIV      = os.getenv("KERN_DISCOVERY_AKTIV", "1") not in ("0", "false", "False")
DEEPSYNC_LIMIT  = 500   # Deep-Sync deckt den ganzen aktiven Bestand ab (~283).
                        # Muss die Zahl aktiver Deals übersteigen. History steckt
                        # im Basis-Token (gratis), daher unkritisch hoch — der
                        # stündliche Preis-Check hält Charts ohnehin schon aktuell.

# Aufgelöst am 15.08.2026 (siehe MIN_PRICE oben): eine Schwelle für alle,
# ergänzt um die Mindestersparnis in Euro. Das Dict bleibt leer stehen, damit
# bestehende Aufrufer (CATEGORY_MIN_PRICE.get(cat, MIN_PRICE)) unverändert
# funktionieren und auf MIN_PRICE zurückfallen.
CATEGORY_MIN_PRICE: dict[str, float] = {}

# Katalog-Qualität (David, 2026-07-06): Preisschwelle NUR für den Katalog-Aufbau
# (seed_bestsellers) 30% über der Deal-Schwelle oben — filtert Billig-/Kleinteil-
# Bestseller raus und schiebt den durchsuchbaren Katalog Richtung hochwertigere,
# teurere Produkte. Rührt NICHT an CATEGORY_MIN_PRICE/MIN_PRICE selbst, die
# bleiben unverändert für die Deal-Discovery.
CATALOG_MIN_PRICE_MULTIPLIER = 1.3

# ---------------------------------------------------------------------------
# Amazon-DE rootCat-ID → Snagga-Kategorie
# Aus Debug-Endpoint /debug/keepa-cats ermittelt (150 Deals, 2026-06-28)
# ---------------------------------------------------------------------------
ROOTCAT_MAP: dict[int, str] = {
    # Auto & Motorrad ist am 15.08.2026 entfallen und steht jetzt in
    # EXCLUDE_ROOTCATS. Kamera & Foto ebenfalls: der Knoten 571860 ist kein
    # Root, sondern ein Kind von Elektronik & Foto — die Snagga-Kategorie
    # konnte sich deshalb nie über rootCat füllen.
    # Spielzeug
    12950651:    "Spielzeug",
    12950661:    "Spielzeug",
    124545011:   "Spielzeug",
    # Gewerbe, Industrie & Wissenschaft (3D-Druck, Messtechnik, Werkstatt)
    5866098031:  "Gewerbe, Industrie & Wissenschaft",
    5866099031:  "Gewerbe, Industrie & Wissenschaft",
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
    # Kosmetik-Knoten (84230031 & Kinder) am 15.08.2026 entfernt: sie brachten
    # Make-Up, Hautpflege und Düfte unter Drogerie & Körperpflege herein, wo
    # genau diese Unterkategorien auf RAUS stehen. Der Root steht jetzt in
    # EXCLUDE_ROOTCATS — einmal blocken statt zweimal filtern.
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
    # Kamera & Foto: Knoten 571860 hängt unter Elektronik & Foto und wird jetzt
    # auch dorthin einsortiert — die eigene Snagga-Kategorie ist entfallen.
    571860:      "Elektronik & Foto",
    # Küche, Haushalt & Wohnen (213083031/213084031/227218031 = Beleuchtung,
    # steht in EXCLUDE_ROOTCATS und ist hier nur noch zur Erinnerung genannt)
    3167641:     "Küche, Haushalt & Wohnen",
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

# ---------------------------------------------------------------------------
# Seed-Knoten-Expansion: ROOTCAT_MAP-Knoten + deren direkte Unterknoten.
# Die Bestseller-Liste eines ROOT-Knotens (z.B. "Elektronik & Foto") ist von
# Billig-Zubehör dominiert (Schutzfolien, Hüllen, Batterien) — echte Produkte
# wie ein iPhone stehen nur in der Bestseller-Liste ihres UNTERknotens
# ("Handys & Smartphones"). Deshalb wird jeder Knoten 1 Ebene tief expandiert.
# Kind-IDs kommen von Keepa /category (1 Token/Knoten) und werden in-memory
# gecacht — der Amazon-Kategoriebaum ändert sich praktisch nie.
# ---------------------------------------------------------------------------
SEED_MAX_CHILDREN_PER_NODE = int(os.getenv("SEED_MAX_CHILDREN_PER_NODE", "25"))
SEED_CHILDREN_TTL_HOURS = int(os.getenv("SEED_CHILDREN_TTL_HOURS", str(24 * 7)))

# Elternknoten-ID → [(Kind-ID, Kind-NAME)]. Der Name kostet nichts extra (Keepa
# liefert ihn im selben Response) und ist die Grundlage der Kern-Discovery: nur
# mit ihm lässt sich „Monitore" von „Computer-Zubehör" unterscheiden.
_seed_children_cache: dict[int, list[tuple[int, str]]] = {}
_seed_children_fetched_at: datetime | None = None


async def _ensure_children_cache(client: httpx.AsyncClient) -> int:
    """
    Füllt _seed_children_cache (Kind-IDs + Namen je ROOTCAT_MAP-Knoten) und gibt
    die verbrauchten Tokens zurück.

    Bewusst als eigener Schritt, weil ihn jetzt ZWEI Jobs brauchen: der
    Katalog-Seed und die stündliche Kern-Discovery. Ohne gemeinsamen Cache
    würde derselbe Kategoriebaum zweimal bezahlt.

    Kostet 1 Token/Elternknoten, läuft aber nur alle SEED_CHILDREN_TTL_HOURS
    (Default: wöchentlich) bzw. nach Neustart — der Amazon-Kategoriebaum ändert
    sich praktisch nie.
    """
    global _seed_children_fetched_at
    tokens_used = 0
    now = datetime.utcnow()

    cache_stale = (
        _seed_children_fetched_at is None
        or (now - _seed_children_fetched_at) > timedelta(hours=SEED_CHILDREN_TTL_HOURS)
    )
    if cache_stale:
        _seed_children_cache.clear()
        _seed_children_fetched_at = None
    # Fehlende Elternknoten (nach TTL-Reset oder gescheiterten Calls) nachholen.
    # cost == 0 heißt Request-Fehler (auch "keine Kinder" kostet 1 Token) →
    # nicht cachen, nächster Lauf versucht es erneut.
    missing = [p for p in ROOTCAT_MAP if p not in _seed_children_cache]
    for parent_id in missing:
        children, cost = await fetch_keepa_category_children_named(
            parent_id, domain=3, client=client)
        tokens_used += cost
        if cost > 0:
            # Ungekürzt cachen: die Kürzung auf SEED_MAX_CHILDREN_PER_NODE ist
            # eine Seed-Sparmassnahme und darf der Kern-Discovery keine Knoten
            # wegnehmen.
            _seed_children_cache[parent_id] = children
    if all(p in _seed_children_cache for p in ROOTCAT_MAP):
        _seed_children_fetched_at = _seed_children_fetched_at or now
    return tokens_used


async def _expanded_seed_nodes(client: httpx.AsyncClient) -> tuple[list[tuple[int, str]], int]:
    """
    Baut die Seed-Knoten-Liste für seed_bestsellers: jeder ROOTCAT_MAP-Knoten
    plus bis zu SEED_MAX_CHILDREN_PER_NODE direkte Unterknoten (gleiche
    Snagga-Kategorie wie der Elternknoten — die endgültige Produkt-Kategorie
    entscheidet ohnehin classify_category).

    Gibt (Liste[(node_id, kategorie)], verbrauchte Tokens) zurück.
    """
    tokens_used = await _ensure_children_cache(client)

    nodes: list[tuple[int, str]] = []
    seen: set[int] = set()
    for parent_id, cat_name in ROOTCAT_MAP.items():
        kinder = [cid for cid, _ in _seed_children_cache.get(parent_id, [])]
        for node_id in [parent_id, *kinder[:SEED_MAX_CHILDREN_PER_NODE]]:
            if node_id in seen or node_id in EXCLUDE_ROOTCATS:
                continue
            seen.add(node_id)
            nodes.append((node_id, cat_name))
    return nodes, tokens_used


async def _kern_knoten(client: httpx.AsyncClient) -> tuple[list[int], int]:
    """
    Keepa-Knoten-IDs der Kern-Unterkategorien — das Fenster, in dem die
    Kern-Discovery sucht (siehe KERN_PAGES oben).

    Abgeglichen wird über den NAMEN: sortiment.kern_namen() liefert die
    gemessenen Namen je Oberkategorie ("monitore", "laptops", …), der
    Kategoriebaum liefert die IDs dazu. Der Umweg über den Namen statt fest
    eingetragener IDs ist Absicht — die Zuordnung Kern/Zubehör wird an genau
    EINER Stelle gepflegt (sortiment.SUBCATEGORY_ROLE), und ein umbenannter
    Amazon-Knoten fällt hier still raus, statt stumm falsche Ware zu liefern.

    ZWEI Ebenen tief (Korrektur David, 15.08.2026) — das war der Grund, warum
    diese Funktion nie einen einzigen Knoten fand:

    Amazons Baum hat zwischen der Root-Kategorie und den eigentlichen
    Unterkategorien eine Zwischenebene ohne inhaltliche Bedeutung. „Computer &
    Zubehör" (340843031) hat nur vier Kinder, und keins davon heisst „Monitore"
    — eines heisst **„Produkte"** (340844031), und erst DARUNTER liegen die 16
    Unterkategorien aus Amazons Bestseller-Leiste. Bei anderen Kategorien heisst
    der Zwischenknoten „Kategorien".

    Die alte Fassung verglich `kern_namen()` gegen genau diese Zwischenebene und
    fand folglich nie einen Treffer. Sie meldete das brav ins Log
    („Kern-Knoten: KEINE gefunden") und übersprang die Abfrage — die Discovery
    lief also die ganze Zeit ausschliesslich über die Root-Knoten, in denen ein
    Laptop im selben Topf liegt wie ein USB-Kabel.

    Gibt (node_ids, verbrauchte Tokens) zurück. Leere Liste = Kern-Discovery
    übersprungen; die Breitensuche läuft unverändert.
    """
    tokens_used = await _ensure_children_cache(client)

    ids: list[int] = []
    gefunden: dict[str, list[str]] = {}
    for parent_id, cat_name in ROOTCAT_MAP.items():
        gesucht = kern_namen(cat_name)
        if not gesucht:
            continue

        # Ebene 1 unter der Root: teils schon die echten Unterkategorien, teils
        # nur der Zwischenknoten. Beides prüfen, statt eine Struktur anzunehmen.
        for cid, name in _seed_children_cache.get(parent_id, []):
            if cid in EXCLUDE_ROOTCATS:
                continue
            if name.strip().lower() in gesucht and cid not in ids:
                ids.append(cid)
                gefunden.setdefault(cat_name, []).append(name)
                continue

            # Kein Namenstreffer → Zwischenknoten. Eine Ebene tiefer schauen.
            # Kostet 1 Token je Zwischenknoten, aber nur bei kaltem Cache
            # (SEED_CHILDREN_TTL_HOURS, Default wöchentlich).
            if cid in _seed_children_cache:
                enkel = _seed_children_cache[cid]
            else:
                enkel, cost = await fetch_keepa_category_children_named(
                    cid, domain=3, client=client)
                tokens_used += cost
                if cost > 0:
                    _seed_children_cache[cid] = enkel
                elif not enkel:
                    continue
            for eid, ename in enkel:
                if eid in EXCLUDE_ROOTCATS or eid in ids:
                    continue
                if ename.strip().lower() in gesucht:
                    ids.append(eid)
                    gefunden.setdefault(cat_name, []).append(ename)

    if ids:
        for cat_name, namen in sorted(gefunden.items()):
            print(f"  Kern-Knoten {cat_name}: {len(namen)} — {', '.join(sorted(namen))}")
        print(f"  Kern-Knoten gesamt: {len(ids)}")
    else:
        # Laut, nicht still: ohne Treffer fällt die Discovery auf die
        # Breitensuche zurück, und das soll im Log sichtbar sein.
        print("  Kern-Knoten: KEINE gefunden — Namen in sortiment.KATEGORIEN "
              "prüfen (Amazon-Knoten umbenannt?). Kern-Abfrage wird übersprungen.")
    return ids, tokens_used


# Explizit ausschließen (rootCat → None, egal was Keywords sagen).
# Stand 15.08.2026 an sortiment.KATEGORIEN angeglichen.
EXCLUDE_ROOTCATS: set[int] = {
    11961464031,  # Bekleidung / Fashion
    340846031,    # Lebensmittel & Getränke
    186606,       # Bücher
    340852031,    # Heimtier
    284266,       # Film/Video/DVD
    255882,       # Musik-Tonträger (Vinyl, CDs)
    355007011,    # Taschen & Accessoires
    192416031,    # Bürobedarf (Stempel, Büromaterial)
    # Am 15.08.2026 gestrichene Oberkategorien — hier explizit blocken, damit
    # sie nicht über den Keyword-Fallback zurückkommen.
    78191031,     # Auto & Motorrad (Modell-Nischenteile)
    79899031,     # Auto & Motorrad
    80931031,     # Auto & Motorrad
    77,           # Auto & Motorrad
    84230031,     # Kosmetik (dupliziert Drogerie & Körperpflege)
    301927,       # Software (keine belastbare Preishistorie)
    213083031,    # Beleuchtung (Unterkategorien laufen unter Küche/Haushalt)
    # 12950651 (Spielzeug) und 5866098031 (Gewerbe/Industrie) standen bis
    # 15.08.2026 hier — beide sind jetzt gewünschte Oberkategorien. Solange sie
    # geblockt waren, konnten LEGO, Playmobil und 3D-Drucker gar nicht ins
    # Schaufenster kommen, egal wie die Kategorie-Tabelle aussah.
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
    "Spielzeug": [
        "lego", "playmobil", "ravensburger", "kosmos experimentierkasten",
        "carrera bahn", "bruder ", "puzzle ", "brettspiel", "gesellschaftsspiel",
        "modellbau", "rc auto", "ferngesteuert",
    ],
    "Gewerbe, Industrie & Wissenschaft": [
        "3d-drucker", "3d drucker", "filament", "resin drucker",
        "messgerät", "multimeter", "oszilloskop", "wärmebildkamera",
        "laserentfernungsmesser", "werkstattwagen",
    ],
    # "Auto & Motorrad" und "Kamera & Foto" am 15.08.2026 entfernt — beide
    # Oberkategorien gibt es nicht mehr. Kamera-Produkte laufen jetzt unter
    # Elektronik & Foto (Unterkategorie "Kamera & Foto" = KERN).
}

# Ausschluss-Keywords: egal was rootCat sagt, diese Produkte nie anzeigen
EXCLUDE_KEYWORDS = [
    # Ausgedünnt am 15.08.2026. Vorher standen hier rund 100 Stichwörter, und
    # gut die Hälfte davon war der Versuch, über Wortraten zu erreichen, was
    # jetzt die RAUS-Rolle in sortiment.KATEGORIEN sauber erledigt:
    #
    #   „spielzeug/lego/puzzle/brettspiel/puppe" → Spielzeug war gesperrt, ist
    #       jetzt gewünscht. Ein „LEGO Technic Bagger" wurde VOR der
    #       Kategorieprüfung verworfen — die Neuaufnahme wäre wirkungslos
    #       geblieben, ohne dass es jemand gemerkt hätte.
    #   „vase/kerzenhalter/bilderrahmen/wandteppich/gardine/…" → deckt
    #       „Wohnaccessoires & Deko" ab, das komplett auf RAUS steht.
    #   „häkelnadel/strickgarn/nähgarn/…" → „Basteln, Malen & Handarbeiten",
    #       ebenfalls RAUS.
    #   „nahrungsergänzung/vitamine/kapsel" → eigene RAUS-Unterkategorien
    #       unter Drogerie & Körperpflege.
    #   „teststreifen/blutzucker/blutdruck" → traf auch Beurer- und
    #       Omron-Messgeräte, also genau die Kernware der Kategorie.
    #
    # Übrig bleibt, was mit der Kategorie NICHTS zu tun hat und deshalb auch
    # nicht über sie zu fassen ist.
    #
    # Kategoriefremde Ware, die über falsche rootCats hereinrutscht:
    "buch ", "bücher", "roman ", "unterwäsche", "unterhose", "socken",
    "t-shirt", "jeans", "hose ", "jacke ", "pullover", "kleidung",
    "schuhe ", "sneaker ",
    "lebensmittel", "kaffee bohnen", "gewürze",
    # Intime / erotische Produkte (Keepas filterErotic greift nicht immer)
    "gleitgel", "lubricant", "kondome", "vibrator",
    # Fahrzeug-/modellspezifische Teile: nie ein Deal für ein breites Publikum,
    # und in JEDER Kategorie ein Ärgernis (Sonnenblende für Nissan XY).
    "passend für", "kompatibel mit", "ersatzteil",
    "für nissan", "für bmw", "für mercedes", "für vw ", "für volkswagen",
    "für audi", "für ford", "für opel", "für toyota", "für honda",
    "für peugeot", "für renault", "für seat", "für skoda", "für hyundai",
    "für kia", "für fiat", "für volvo", "für mazda", "für suzuki",
    # Tastaturen/Eingabegeräte mit nicht-DACH-Layout (Amazon trennt das nicht
    # per Kategorie, und ein US-Layout ist für D-A-CH schlicht unbrauchbar)
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
        return _nur_bekannte(_reroute_peripheral(ROOTCAT_MAP[root_cat], title_l))

    # 4. Keyword-Fallback (exhaustiv — kein Catch-all mehr)
    for cat, pattern in _KEYWORD_RE.items():
        if pattern.search(title_l):
            return _nur_bekannte(_reroute_peripheral(cat, title_l))

    # 5. Kein Match → ablehnen
    return None


def _nur_bekannte(cat: str | None) -> str | None:
    """
    Lässt nur Kategorien durch, die in sortiment.KATEGORIEN stehen.

    Der strukturelle Riegel gegen genau den Fehler, der diesen Umbau nötig
    machte: Kategorie-Wissen lag an vier Stellen verteilt und lief auseinander.
    Am 15.08.2026 vergab ROOTCAT_MAP noch „Auto & Motorrad" und „Kamera & Foto",
    obwohl beide gestrichen waren — die Produkte kamen weiter herein, und weil
    sortiment.rolle() für unbekannte Oberkategorien UNBEKANNT liefert, griff
    auch die RAUS-Regel nicht.

    Mit dieser Zeile ist die Tabelle die letzte Instanz: wer dort keine
    Oberkategorie hat, wird nicht angezeigt — egal was ROOTCAT_MAP oder die
    Keyword-Listen sagen.
    """
    if cat and cat in KATEGORIEN:
        return cat
    return None


# ---------------------------------------------------------------------------
# Stündlicher Preis-Check via Keepa /product (~1 Token/ASIN, History inklusive)
# ---------------------------------------------------------------------------

async def hourly_keepa_price_check():
    """
    Prüft die Preise aktiver Deals via Keepa /product — inkl. voller Preishistorie
    (die im Basis-Token gratis ist). Jedes geprüfte Produkt bekommt so einen
    aktuellen Chart; ein separater History-Backfill ist nicht mehr nötig.

    Gestaffelt:
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
            "SELECT asin, name, brand, current_price, avg90_price, avg180_price, all_time_low, "
            "atl_confirmed, category, sub_category, rating, reviews, sales_rank FROM products "
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

    asins = [row["asin"] for row in active]
    # History ist im Basis-Token gratis → gleich die vollen Produktdaten inkl.
    # Preisverlauf holen und speichern, damit jedes geprüfte Produkt einen
    # aktuellen Chart hat (ersetzt den früheren separaten History-Backfill).
    enriched = await enrich_with_keepa(asins, domain=3)

    if not enriched:
        print("  Keepa Preis-Check: keine Preisdaten erhalten — Abbruch")
        return
    current_prices = {a: kd["current_price"] for a, kd in enriched.items() if kd.get("current_price")}

    # Volatilität: Anzahl Preissprünge >3% über die letzten 12 gespeicherten Punkte.
    # Reihenfolge per id (monoton) statt Zeitstempel (price_history.timestamp ist TEXT).
    move_counts = await _count_price_moves(asins)

    deactivated = volatile_cnt = ohne_preis = 0
    async with db.acquire() as conn:
        for row in active:
            asin       = row["asin"]
            live_price = current_prices.get(asin)
            if live_price is None:
                # Keepa kennt gerade keinen brauchbaren Preis (kein Angebot,
                # keine Buy Box). `last_checked` trotzdem setzen — sonst bleibt
                # die Zeile für die Tier-Abfrage oben dauerhaft „fällig" und
                # wird JEDE Stunde erneut abgefragt, für immer, ein Token pro
                # Lauf (Fund 16.08.2026 am Olympus-Objektiv für 793 €).
                #
                # `last_updated` bleibt bewusst unangetastet: es ist der Beleg
                # „zuletzt bestätigt", und bestätigt wurde hier nichts. Genau
                # daran greift die Karenz-Regel weiter unten.
                ohne_preis += 1
                await conn.execute(
                    "UPDATE products SET last_checked=$2 WHERE asin=$1", asin, now)
                continue

            avg90  = row["avg90_price"]  or 0.0
            avg180 = row["avg180_price"] or 0.0
            atl    = row["all_time_low"] or 0.0

            # Unterkategorie aus der FRISCHEN Keepa-Antwort, nicht aus der
            # DB-Zeile (Korrektur 16.08.2026).
            #
            # Vorher lief der Hard-Filter gegen `row["sub_category"]` — den Wert,
            # der beim Laden der Zeile in der DB stand. Bei einem frisch
            # entdeckten Deal ist der leer, denn Keepas /deal liefert keine
            # Unterkategorie. `ist_raus()` gibt bei leerem Wert bewusst False
            # zurück, der Deal besteht also. Erst UNTEN im else-Zweig wurde
            # `sub_category` geschrieben — die RAUS-Prüfung fand also frühestens
            # beim ÜBERNÄCHSTEN Lauf statt.
            #
            # Praktisch heisst das: bis zu fünf Stunden sichtbar. Die untere
            # Tier-Stufe wird nur alle vier Stunden fällig, dazu die Stunde bis
            # zum nächsten Job. Gemessen am 16.08.2026 standen dadurch sechs
            # aktive Deals in „Wohnaccessoires & Deko" — einer Unterkategorie,
            # die auf RAUS steht: vier Carpettex-Teppiche und zwei weitere, elf
            # Prozent des ganzen Schaufensters.
            #
            # `kd` liegt hier bereits vor (enriched wurde vor der Schleife
            # geholt). Die Prüfung kostet also nichts extra und greift beim
            # ERSTEN Check nach der Entdeckung.
            kd       = enriched.get(asin) or {}
            sub_cat  = (kd.get("sub_category") or "").strip() or (
                (row["sub_category"] or "") if "sub_category" in row.keys() else "")

            volatile = move_counts.get(asin, 0) >= 3
            if volatile:
                volatile_cnt += 1

            # Volatil UND schwacher Rabatt (kaum unter avg90) → faul, raus.
            weak_volatile = volatile and avg90 > 0 and live_price > avg90 * 0.95

            # avg30 kennt die products-Tabelle nicht (nur avg90_price und
            # avg180_price aus /product) → 0 = Anti-Spike hier übersprungen. Er
            # hat bei der Aufnahme bereits gegriffen; hier geht es darum, ob der
            # Deal noch gut IST, nicht ob er es je war.
            #
            # Der stündliche Check ist ausserdem die einzige Stelle, an der die
            # Unterkategorie vorliegt — /deal liefert sie nicht. Die RAUS-Regel
            # greift deshalb erst hier: ein Produkt aus „Sportmedizin" oder
            # „Wohnaccessoires & Deko" verschwindet beim nächsten Lauf.
            if weak_volatile or not passes_hard_filters(
                row["rating"], row["reviews"], row["sales_rank"] or 0,
                row["category"], live_price, avg90,
                atl=atl, avg30=0.0,
                title=row["name"] or "",
                brand=(row["brand"] or "") if "brand" in row.keys() else "",
                atl_ist_beleg=bool(row["atl_confirmed"]),
                sub_category=sub_cat,
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
                    title=row["name"] or "",
                )
                # Echte History (gratis im Basis-Token) → konkretes Kachel-Urteil
                # "Bester Preis seit X Monaten" statt nur Rabatt-Prozent.
                # (`kd` steht schon oben zur Verfügung — siehe sub_cat.)
                hist = kd.get("history") or []
                months = best_price_since_months(hist, live_price)
                # Allzeittief ausschliesslich über resolve_atl(). Vorher stand hier
                # min(gespeichertes atl, keepa atl, live_price) mit fest
                # atl_confirmed=True — zwei Fehler in einer Zeile: der aktuelle Preis
                # war Kandidat (das Tief lag damit nie über ihm, der Claim konnte nicht
                # mehr fehlschlagen) UND der gespeicherte Wert war womöglich der
                # avg365-Proxy aus /deal, der so zum „bestätigten" Tief wurde.
                # Ergebnis: 30,56 € wurde als Allzeittief beworben, obwohl der Chart
                # daneben 22,59 € zeigte.
                atl_now, atl_ok = resolve_atl(
                    live_price,
                    keepa_atl=kd.get("all_time_low") or 0.0,
                    stored_atl=atl,
                    stored_confirmed=bool(row["atl_confirmed"]),
                    history_prices=[pr for pr, _ in hist if pr and pr > 0],
                    history_span_days=historien_spanne_tage(hist),
                )
                tag = determine_tag(live_price, atl_now, avg90, avg180,
                                    atl_confirmed=atl_ok, months_since_lower=months)
                # last_updated wird mit-refresht: bestätigt-gute Deals laufen nicht aus,
                # auch wenn Keepa sie nicht mehr als "frischen" Deal im /deal-Stream meldet.
                # (Volatilität steuert oben nur die weak_volatile-Deaktivierung; die
                #  Prüf-Frequenz ergibt sich aus deal_score-Perzentil + last_checked.)
                # all_time_low/atl_confirmed aus derselben resolve_atl()-Momentaufnahme
                # wie der Tag → angezeigte Zahl und Badge können nicht auseinanderlaufen.
                # Ist das Tief unbelegt, bleibt der gespeicherte (Proxy-)Wert für die
                # Score-Berechnung stehen, wird aber NICHT als belegt markiert.
                # sub_category wird hier mitgeschrieben (Fund 11.08.2026): der
                # /deal-Endpoint liefert keine Kategorieebene 2, und dieser
                # Preis-Check war der einzige Pfad, den ein frisch entdeckter
                # Deal durchläuft — er hatte `kd` mit der Unterkategorie in der
                # Hand und verwarf sie. Ergebnis: 95 von 114 aktiven Deals ohne
                # Unterkategorie, während der Katalog sie sauber gefüllt hatte.
                # Ohne dieses Feld ist keine Sortiments-Steuerung möglich.
                await conn.execute(
                    "UPDATE products SET current_price=$2, deal_score=$3, tag=$4, "
                    "last_checked=$5, last_updated=$5, score_breakdown=$6, "
                    "all_time_low = CASE WHEN $8 THEN $7 ELSE all_time_low END, "
                    "atl_confirmed = $8, "
                    "sub_category = CASE WHEN $9 != '' THEN $9 ELSE sub_category END, "
                    "sub_category2 = CASE WHEN $10 != '' THEN $10 ELSE sub_category2 END "
                    "WHERE asin=$1",
                    asin, live_price, score, tag, now, breakdown, atl_now, atl_ok,
                    (kd.get("sub_category") or "") if kd else "",
                    (kd.get("sub_category2") or "") if kd else "",
                )

                # Kostenlose Keepa-History einspielen → Chart aktuell, Marke mitnehmen.
                # (kd/hist wurden oben schon für das Kachel-Urteil geholt.)
                if hist:
                    recent = hist[-2000:]  # volle History speichern (Chart-Default zeigt 365 Tage)
                    await conn.execute("DELETE FROM price_history WHERE asin=$1", asin)
                    await conn.executemany(
                        "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                        [(asin, pr, ts) for pr, ts in recent],
                    )
                    await conn.execute(
                        "UPDATE products SET has_real_history=true, "
                        "brand = CASE WHEN $2 != '' THEN $2 ELSE brand END WHERE asin=$1",
                        asin, kd.get("brand") or "",
                    )
                else:
                    await conn.execute(
                        "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                        asin, live_price, now,
                    )
                    # Bug (gefunden 2026-07-06): dieser Zweig setzte has_real_history
                    # NIE, obwohl über viele stündliche Checks hinweg echte Punkte
                    # entstehen — Produkte blieben für immer chartlos, obwohl >=2
                    # echte Preispunkte längst da waren. Sobald genug zusammenkamen,
                    # jetzt Chart aktivieren (dieselbe Schwelle wie _price_chart_svg).
                    cnt = await conn.fetchval(
                        "SELECT count(*) FROM price_history WHERE asin=$1", asin
                    )
                    if cnt >= 2:
                        await conn.execute(
                            "UPDATE products SET has_real_history=true WHERE asin=$1", asin
                        )

        # ── Invariante: kein aktiver Deal ohne Chart ────────────────────────
        # Gemessen am 11.08.2026: 23 von 92 aktiven Deals hatten kein belegtes
        # Tief und keine echte Historie. Ursache ist die Zeile `if live_price is
        # None: continue` weiter oben — Produkte, für die Keepas /product nichts
        # Brauchbares liefert, werden stillschweigend übersprungen. Sie bekommen
        # nie ein last_checked, laufen deshalb jede Stunde erneut in dieselbe
        # Lücke und bleiben dauerhaft aktiv: chartlos, mit einem Tag, der nur auf
        # den /deal-Durchschnitten beruht.
        #
        # snagga wirbt damit, dass jeder Preis gegen die echte Historie geprüft
        # ist. Ein Deal ohne Chart kann dieses Versprechen nicht einlösen, also
        # gehört er nicht ins Schaufenster. Nach der Karenzzeit (der stündliche
        # Check hat dann mehrfach vergeblich versucht, Historie zu holen) wird er
        # deaktiviert; die Seite bleibt erreichbar, der Deal verschwindet nur aus
        # der Liste. Nachrücken übernehmen die Backups.
        chartless = await conn.fetch(
            "UPDATE products SET is_active=false, is_top_pick=false "
            "WHERE is_active=true AND has_real_history=false "
            "  AND COALESCE(first_seen, last_updated) < NOW() - make_interval(hours => $1) "
            "RETURNING asin",
            CHART_GRACE_HOURS,
        )
        if chartless:
            deactivated += len(chartless)
            print(f"  Ohne Chart nach {CHART_GRACE_HOURS}h deaktiviert: {len(chartless)} "
                  f"({', '.join(r['asin'] for r in chartless[:8])}"
                  f"{' …' if len(chartless) > 8 else ''})")

        # ── Invariante: kein aktiver Deal ohne frische Bestätigung ──────────
        # Gegenstück zur Chart-Invariante darüber, und aus demselben Grund
        # nötig (Fund 16.08.2026): Ein Objektiv für 793 € stand aktiv im
        # Schaufenster — mit rating 0.0, reviews 0 und 1,3 % Abstand zum Ø90.
        # Es hätte an drei Hard-Filtern scheitern müssen, wurde aber nie wieder
        # geprüft, weil `live_price is None` es jede Stunde stumm übersprang.
        #
        # Bisher hing das Aufräumen an zwei Stellen, die beide nicht greifen:
        # die Chart-Invariante prüft nur `has_real_history=false`, und die
        # 4-Stunden-Regel in fetch_and_update_deals() läuft im ANDEREN Job —
        # bricht der ab (Keepa liefert nichts, `if not got_any: return`), räumt
        # niemand auf.
        #
        # Deshalb hier, im Job, der ohnehin dafür zuständig ist zu entscheiden,
        # ob ein Deal noch gut IST: Was seit PREIS_GRACE_HOURS von keiner Seite
        # mehr bestätigt wurde, verschwindet aus der Liste. Die /preis-Seite
        # bleibt erreichbar, Backups rücken nach.
        veraltet = await conn.fetch(
            "UPDATE products SET is_active=false, is_top_pick=false "
            "WHERE is_active=true "
            "  AND COALESCE(last_updated, first_seen) < NOW() - make_interval(hours => $1) "
            "RETURNING asin",
            PREIS_GRACE_HOURS,
        )
        if veraltet:
            deactivated += len(veraltet)
            print(f"  Ohne Bestätigung seit {PREIS_GRACE_HOURS}h deaktiviert: "
                  f"{len(veraltet)} ({', '.join(r['asin'] for r in veraltet[:8])}"
                  f"{' …' if len(veraltet) > 8 else ''})")

        # Reihenfolge zählt: erst die gestrichenen Kategorien räumen, dann die
        # Quote rechnen. Andersherum würde die Quote noch gegen Deals rechnen,
        # die gleich ohnehin verschwinden, und zu viel Zubehör deaktivieren.
        deactivated += await _gestrichene_kategorien_deaktivieren(conn)
        deactivated += await _sortiment_quote_durchsetzen(conn)

    if deactivated > 0:
        await _promote_backups_simple(deactivated)

    await _recalculate_top_picks()
    print(f"  Keepa Preis-Check fertig: {deactivated} deaktiviert "
          f"({volatile_cnt} volatil), {len(current_prices)} geprüft"
          f"{f', {ohne_preis} ohne Preis' if ohne_preis else ''}.")


VARIANTEN_WORTE = int(os.getenv("VARIANTEN_WORTE", "5"))


def _varianten_schluessel(titel: str) -> str:
    """
    Erzeugt einen groben Produktschlüssel aus den ersten Titelwörtern.

    Amazon führt Farben, Größen und Speicherausbauten als eigene ASINs mit
    eigenem Preis — für Keepa sind das verschiedene Produkte, für den Besucher
    dreimal dasselbe. Der Titel beginnt praktisch immer mit Marke und Modell und
    unterscheidet sich erst danach ("… Space 2, Schwarz" / "… Space 2, Blau"),
    deshalb genügen die ersten `VARIANTEN_WORTE` Wörter.

    Bewusst grob gehalten: lieber gelegentlich zwei echte Geschwistermodelle
    zusammenfassen (wir verlieren einen Deal von vielen) als das Schaufenster
    mit Dubletten zu füllen — gemessen am 12.08.2026 standen dieselben
    soundcore-Kopfhörer dreimal und iPhone-Hüllen mehrfach in der Liste.
    """
    worte = re.findall(r"[a-z0-9äöüß]+", (titel or "").lower())
    return " ".join(worte[:VARIANTEN_WORTE])


# Rang-Toleranz für die zweite Variantenprüfung (siehe _varianten_entdoppeln).
# Amazon führt Farb- und Größenvarianten als eigene ASINs, die sich den
# Verkaufsrang des Elternprodukts teilen — gemessen am 16.08.2026 an drei
# Carpettex-Teppichen: 5678, 5677, 5677. Eine kleine absolute Toleranz reicht;
# grösser gefasst träfe sie zufällig gleichplatzierte Fremdprodukte.
VARIANTEN_RANG_TOLERANZ = int(os.getenv("VARIANTEN_RANG_TOLERANZ", "5"))


def _marken_schluessel(kandidat: dict) -> str:
    """
    Marke klein geschrieben; ersatzweise das erste Titelwort.

    Der /deal-Endpoint liefert `brand` oft leer, der Titel beginnt bei Amazon
    aber praktisch immer mit der Marke — dieselbe Annahme, auf der schon
    scoring.is_known_brand() aufbaut.
    """
    b = (kandidat.get("brand") or "").strip().lower()
    if b:
        return b
    worte = re.findall(r"[a-z0-9äöüß]+", (kandidat.get("title") or "").lower())
    return worte[0] if worte else ""


def _varianten_entdoppeln(kandidaten: list[dict]) -> tuple[list[dict], int]:
    """
    Behält je Produktschlüssel nur den besten Kandidaten. Erwartet eine bereits
    nach Score absteigend sortierte Liste — der erste Treffer ist damit der
    beste, alle weiteren sind Farb-/Größenvarianten mit schlechterem Angebot.
    Gibt (bereinigte Liste, Anzahl entfernter Dubletten) zurück.

    ZWEI Prüfungen seit 16.08.2026, weil die erste allein nicht reicht:

      1. Titelanfang (_varianten_schluessel) — greift, solange sich Varianten
         erst hinten unterscheiden ("… Space 2, Schwarz" / "… Space 2, Blau").
      2. Marke + fast gleicher Verkaufsrang — greift, wenn Farbe und Maß schon
         im Titelanfang stehen und die erste Prüfung damit ins Leere läuft.

    Auslöser für (2): Im Lauf um 11:05 kamen vier Teppiche herein, drei davon
    aus derselben Carpettex-Serie — „Carpettex Teppich Rot 200x280 cm",
    „… Weiss 240x340 cm", „… Rund Beige 200 cm". Die ersten fünf Wörter gehen
    auseinander, der Verkaufsrang aber kaum: 5678, 5677, 5677. Genau dieser
    Fingerabdruck steht schon in sortiment.py bei „gartendeko" beschrieben
    (13 von 15 Treffern Kunstrasen-Meterware desselben Anbieters, alle mit Rang
    12188) — er war nur nie ausgewertet.

    Bewusst eng gefasst: nur bei gleicher Marke UND einem Rangabstand von
    höchstens VARIANTEN_RANG_TOLERANZ. Zwei verschiedene Bosch-Werkzeuge mit
    zufällig fünf Rängen Abstand sind selten; eine ganze Teppichserie mit
    identischem Rang ist es nicht.
    """
    gesehen: set[str] = set()
    # Marke → Ränge der bereits behaltenen Kandidaten dieser Marke. Als Dict,
    # damit nicht bei jedem Kandidaten die ganze behaltene Liste durchlaufen
    # werden muss (die Discovery prüft bis zu 2.400 Stück pro Lauf).
    raenge_je_marke: dict[str, list[int]] = {}
    behalten: list[dict] = []
    for k in kandidaten:
        schluessel = _varianten_schluessel(k.get("title") or "")
        if schluessel and schluessel in gesehen:
            continue

        marke = _marken_schluessel(k)
        rang  = int(k.get("sales_rank") or 0)
        if marke and rang > 0 and any(
            abs(rang - r) <= VARIANTEN_RANG_TOLERANZ for r in raenge_je_marke.get(marke, ())
        ):
            continue

        if schluessel:
            gesehen.add(schluessel)
        if marke and rang > 0:
            raenge_je_marke.setdefault(marke, []).append(rang)
        behalten.append(k)
    return behalten, len(kandidaten) - len(behalten)


async def _gestrichene_kategorien_deaktivieren(conn) -> int:
    """
    Deaktiviert aktive Deals, deren Oberkategorie es nicht mehr gibt.

    Warum das eine eigene Regel braucht (David, 15.08.2026): Wird eine Kategorie
    gestrichen, hört die Discovery auf, dorthin zu greifen — die BEREITS aktiven
    Produkte bleiben aber liegen. Und sie sind gegen alle neuen Regeln immun:
    `sortiment.rolle()` liefert für eine unbekannte Oberkategorie UNBEKANNT,
    also greift weder RAUS noch die Zubehör-Quote. Ein aktiver „Auto &
    Motorrad"-Deal bliebe stehen, bis er zufällig an Preis oder Rang scheitert.

    Betrifft nicht nur den Umbau vom 15.08.2026: die Datenbank trägt auch
    Kategorien aus früheren Iterationen („Beauty", „Gaming", „Haushalt",
    „Küche", „Sport", „Sonstiges"), die nie aufgeräumt wurden.

    Die /preis-Seiten dieser Produkte bleiben erreichbar — sie verschwinden nur
    aus dem Schaufenster. Katalogseiten sind SEO-Substanz, die man nicht wegen
    einer Sortimentsentscheidung wegwirft.
    """
    rows = await conn.fetch(
        "SELECT DISTINCT category FROM products WHERE is_active=true")
    weg = [r["category"] for r in rows if (r["category"] or "") not in KATEGORIEN]
    if not weg:
        return 0

    result = await conn.fetch(
        "UPDATE products SET is_active=false, is_top_pick=false "
        "WHERE is_active=true AND category = ANY($1::text[]) RETURNING asin",
        weg)
    if result:
        print(f"  Gestrichene Kategorien deaktiviert: {len(result)} "
              f"({', '.join(sorted(weg))})")
    return len(result)


async def _sortiment_quote_durchsetzen(conn) -> int:
    """
    Sorgt dafür, dass eine Kategorie zeigt, was ihr Name verspricht: Zubehör
    darf höchstens den in `sortiment.MAX_ZUBEHOER_ANTEIL` erlaubten Anteil der
    aktiven Deals stellen. Überzähliges Zubehör wird deaktiviert, das mit dem
    niedrigsten Score zuerst.

    Warum hier und nicht bei der Entdeckung: die Unterkategorie kommt aus Keepas
    `/product` und ist im `/deal`-Stream noch unbekannt. Erst nach dem
    Preis-Check oben steht sie zur Verfügung.

    Warum deaktivieren statt umsortieren: die Kachelreihenfolge entsteht im
    Frontend nach Score. Ein Kleinteil, das nur nach hinten rutscht, ist auf der
    Kategorieseite trotzdem sichtbar — David hat genau das bemängelt. Die
    `/preis`-Seite bleibt selbstverständlich erreichbar, das Produkt verschwindet
    nur aus dem Schaufenster, und Backups rücken nach.
    """
    import sortiment

    if not (sortiment.QUOTA_AKTIV and sortiment.ist_konfiguriert()):
        return 0

    rows = await conn.fetch(
        "SELECT asin, category, COALESCE(sub_category,'') AS sub, deal_score "
        "FROM products WHERE is_active=true"
    )

    nach_kategorie: dict[str, list] = {}
    for r in rows:
        nach_kategorie.setdefault(r["category"] or "", []).append(r)

    raus: list[str] = []
    for cat, items in nach_kategorie.items():
        zubehoer = [r for r in items if sortiment.rolle(cat, r["sub"]) == sortiment.ZUBEHOER]
        ueber = sortiment.zuviel_zubehoer(cat, len(zubehoer), len(items))
        if ueber <= 0:
            continue
        zubehoer.sort(key=lambda r: r["deal_score"] or 0)
        weg = [r["asin"] for r in zubehoer[:ueber]]
        raus.extend(weg)
        print(f"  Sortiment {cat}: {len(zubehoer)}/{len(items)} Zubehör → "
              f"{len(weg)} deaktiviert")

    if not raus:
        return 0

    await conn.execute(
        "UPDATE products SET is_active=false, is_top_pick=false "
        "WHERE asin = ANY($1::text[])", raus)
    return len(raus)


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
    """
    Rückt die besten Backup-Deals vor.

    `last_updated` wird dabei auf jetzt gesetzt und `last_checked` auf NULL
    (Ergänzung 16.08.2026, zusammen mit PREIS_GRACE_HOURS):

      * `last_updated` ist die Uhr der Karenz-Regel. Ein Backup, das ein paar
        Stunden gelegen hat, wäre sonst im selben Moment wieder deaktiviert, in
        dem es vorrückt — und beim nächsten Lauf erneut befördert. Genau die
        Sorte Rückkopplung, die schon bei der Zubehör-Quote für stündliches
        Zappeln gesorgt hat (siehe sortiment.zuviel_zubehoer).
      * `last_checked=NULL` sorgt dafür, dass die Tier-Abfrage des Preis-Checks
        das Produkt beim nächsten Lauf ZUERST greift. Vorgerückt wird ohne
        erneute Preis-Verifikation — sie wird damit unmittelbar nachgeholt,
        lange innerhalb der Karenzzeit.
    """
    db = await get_pool()
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE products SET is_active=true, is_backup=false, "
            "  last_updated=NOW(), last_checked=NULL "
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

        # Beobachtungsprotokoll: JEDER Kandidat wird hier gesammelt — auch die
        # gleich wieder verworfenen. `products` enthält nur die Gewinner, damit
        # fehlt jeder Quotenaussage der Nenner (siehe CREATE_DEAL_OBSERVATIONS in
        # database.py). Geschrieben wird gebündelt nach dem Durchlauf, damit die
        # synchrone process()-Schleife nichts awaiten muss.
        observations: list[tuple] = []
        obs_seen: set[str] = set()
        # Welche Hard-Filter-Bedingung wie oft greift — ohne das sagt das Log nur
        # "N durch HardFilter aussortiert" und man justiert blind nach.
        hf_breakdown: dict[str, int] = {}

        def observe(d, cat, accepted: bool, reason: str = ""):
            if d["asin"] in obs_seen:
                return
            obs_seen.add(d["asin"])
            observations.append((
                d["asin"], cat or "", d["current_price"],
                # Spaltennamen im Protokoll bleiben (avg30/avg90/avg180/avg365),
                # gefüllt werden sie ab 15.08.2026 mit dem, was /deal wirklich
                # liefert: Ø7d, Ø90d, Ø30d, Ø48h. Umbenennen hiesse die Tabelle
                # migrieren; der Erkenntniswert liegt im Vergleich der Zeiträume,
                # nicht im Spaltennamen.
                d.get("avg7") or 0.0, d.get("avg90") or 0.0, d.get("avg30") or 0.0,
                d.get("avg48h") or 0.0,
                d.get("list_price") or 0.0,
                int(d.get("delta_pct") or 0),
                d.get("rating") or 0.0, int(d.get("reviews") or 0),
                accepted, reason,
            ))

        # ── 2. Hard Filters + Scoring (pro Seite, gemeinsam für beide Abfragen) ──
        def process(page_deals):
            nonlocal skipped_cat, skipped_price, skipped_filter, skipped_score
            for d in page_deals:
                if d["asin"] in seen_asins:
                    continue  # Dedup: Elektronik-Zusatzabfrage überschneidet sich mit Hauptabfrage
                if d["current_price"] < MIN_PRICE:
                    skipped_price += 1
                    observe(d, None, False, "preis_min")
                    continue

                cat = classify_category(d["title"] or d["brand"], d.get("root_cat", 0))
                if cat is None:
                    skipped_cat += 1
                    observe(d, None, False, "kategorie_unbekannt")
                    continue
                d["category"] = cat

                cat_min = CATEGORY_MIN_PRICE.get(cat, MIN_PRICE)
                if d["current_price"] < cat_min:
                    skipped_price += 1
                    observe(d, cat, False, "preis_min_kategorie")
                    continue

                hf_reason = hard_filter_reason(
                    d["rating"], d["reviews"], d["sales_rank"], cat,
                    d["current_price"], d["avg90"],
                    atl=0.0, avg30=d.get("avg30") or 0.0,
                    title=d["title"] or "",
                    brand=d.get("brand") or "",
                    # /deal liefert kein Allzeittief und keine Unterkategorie.
                    # Beides kommt erst mit /product; die RAUS-Prüfung holt der
                    # stündliche Preis-Check nach.
                    atl_ist_beleg=False,
                    sub_category="",
                )
                if hf_reason:
                    skipped_filter += 1
                    hf_breakdown[hf_reason] = hf_breakdown.get(hf_reason, 0) + 1
                    observe(d, cat, False, f"hard_filter:{hf_reason}")
                    continue

                score, breakdown = calculate_deal_score(
                    d["current_price"], d["avg90"], 0.0,
                    d["sales_rank"], cat,
                    d["rating"], d["reviews"],
                    price_updated=None,
                    title=d["title"] or "",
                )
                if score < MIN_SCORE:
                    skipped_score += 1
                    observe(d, cat, False, "score_zu_niedrig")
                    continue

                observe(d, cat, True)

                d["deal_score"]      = score
                d["score_breakdown"] = breakdown
                # Kein Tief-Beleg aus /deal → atl=0, atl_confirmed=False. Der Tag
                # entsteht hier allein aus dem Ø90-Vergleich; ein belegtes Tief
                # liefert erst der Preis-Check/Deep-Sync via /product.
                d["tag"]             = determine_tag(d["current_price"], 0.0, d["avg90"], 0.0,
                                                     atl_confirmed=False)
                # Durchgestrichener Preis = 90-Tage-Ø, also exakt die Referenz,
                # gegen die auch gefiltert wird. Vorher stand hier avg180 — ein
                # Wert, der in Wahrheit der 30-Tage-Schnitt war und damit weder
                # zum Tooltip („6 Monate") noch zur Filterregel passte. Ein Preis
                # auf der Kachel und die Zahl, gegen die geprüft wurde, sind ab
                # jetzt dieselbe.
                d["original_price"]  = d["avg90"] or round(d["current_price"] * 1.25, 2)
                d["avg_price"]       = d["avg90"] or d["current_price"]
                seen_asins.add(d["asin"])
                candidates.append(d)

        # ── Discovery, neu geordnet (David, 15.08.2026) ─────────────────────
        # Vorher liefen hier VIER überlappende Abfragen (Whitelist −15 %,
        # Elektronik −10 %, Hochpreis ab 100 €, Kern-Knoten −8 %). Sie waren
        # nacheinander entstanden, jede als Reparatur der vorigen, und holten
        # sich gegenseitig dieselben Kandidaten. Vor allem aber lief die einzige
        # zielgenaue davon — die Kern-Abfrage — faktisch nie: `_kern_knoten()`
        # suchte auf der falschen Baumebene und fand nie einen Knoten.
        #
        # Jetzt zwei Abfragen mit klarer Aufgabenteilung:

        # 1. KERN-ABFRAGE — die eigentliche Suche.
        #    Fenster sind die Unterkategorien, die in sortiment.KATEGORIEN auf
        #    KERN stehen: Monitore, Laptops, Elektrische Küchengeräte, Elektro-
        #    & Handwerkzeuge, Bau- & Konstruktionsspielzeug …
        #    Keepas Sortierung nach Rabatt-Prozent wird damit vom Problem zum
        #    Vorteil: innerhalb eines Kern-Knotens stehen oben die besten
        #    Zeitpunkte für genau die Ware, die wir zeigen wollen.
        kern_ids: list[int] = []
        if KERN_AKTIV:
            kern_ids, kern_tokens = await _kern_knoten(client)
            if kern_tokens:
                print(f"  Kategoriebaum: {kern_tokens} Tokens (nur bei kaltem Cache)")
        for start in range(0, len(kern_ids), KERN_BATCH):
            batch = kern_ids[start:start + KERN_BATCH]
            for page in range(KERN_PAGES):
                page_deals = await fetch_keepa_deals(
                    domain=3, delta_pct=KERN_DELTA_PCT, min_rating=40, min_reviews=50,
                    page=page, client=client, include_cats=batch,
                    min_price_cents=int(MIN_PRICE * 100),
                )
                if not page_deals:
                    break
                got_any = True
                process(page_deals)
        kern_treffer = len(candidates)
        if kern_ids:
            print(f"  Kern-Abfrage: {len(kern_ids)} Knoten · {kern_treffer} qualifizierte Deals")

        # 2. BREITENSUCHE — Auffangnetz, keine Hauptquelle.
        #    Deckt ab, was die Kern-Knoten nicht erfassen: umbenannte Knoten,
        #    Ware in noch nicht eingeordneten Unterkategorien, und den Fall,
        #    dass die Namensauflösung ganz scheitert. Läuft über dieselbe
        #    Root-Whitelist wie früher, aber mit derselben Schwelle wie überall
        #    sonst — die vier verschiedenen Prozentwerte sind entfallen.
        #    Die Dedup über seen_asins hält die Kern-Treffer.
        for page in range(DEAL_PAGES):
            page_deals = await fetch_keepa_deals(
                domain=3, delta_pct=DEAL_DELTA_PCT, min_rating=40, min_reviews=50,
                page=page, client=client,
                min_price_cents=int(MIN_PRICE * 100),
            )
            if not page_deals:
                break
            got_any = True
            process(page_deals)
        print(f"  Breitensuche: {len(candidates) - kern_treffer} zusätzliche Deals")

        if not got_any:
            print("  Keepa /deals lieferte keine Daten — Abbruch.")
            return 0

        # Sortieren nach Score
        candidates.sort(key=lambda x: x["deal_score"], reverse=True)
        candidates, dubletten = _varianten_entdoppeln(candidates)
        if dubletten:
            print(f"  Varianten-Dubletten entfernt: {dubletten}")
        active_pool = candidates[:MAX_ACTIVE]
        backup_pool = candidates[MAX_ACTIVE : MAX_ACTIVE + MAX_BACKUP]

        print(
            f"  Gefiltert: {skipped_price} Preis<{MIN_PRICE}€ · "
            f"{skipped_cat} unbekannte Kat · {skipped_filter} HardFilter · {skipped_score} Score"
        )
        if hf_breakdown:
            _hf = " · ".join(f"{k}:{v}" for k, v in
                             sorted(hf_breakdown.items(), key=lambda kv: -kv[1]))
            print(f"  HardFilter im Detail: {_hf}")
        print(f"  {len(candidates)} qualifiziert · {len(active_pool)} aktiv · {len(backup_pool)} Backup")

        # ── 3. DB schreiben ──────────────────────────────────────────────────
        db = await get_pool()
        async with db.acquire() as conn:

            # Beobachtungsprotokoll zuerst und bewusst fehlertolerant: es ist reine
            # Auswertungs-Nebenwirkung. Schlägt es fehl, darf der Deal-Job trotzdem
            # durchlaufen — Deals auszuliefern ist wichtiger als die Statistik.
            # ON CONFLICT DO NOTHING greift über UNIQUE(asin, observed_day): der Job
            # läuft stündlich, gespeichert wird die erste Beobachtung des Tages.
            if observations:
                try:
                    await conn.executemany(
                        "INSERT INTO deal_observations "
                        "(asin, observed_day, category, current_price, avg30, avg90, avg180, "
                        " avg365, list_price, claimed_pct, rating, reviews, accepted, reject_reason) "
                        "VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) "
                        "ON CONFLICT (asin, observed_day) DO NOTHING",
                        observations,
                    )
                    _acc = sum(1 for o in observations if o[-2])
                    print(f"  Beobachtungsprotokoll: {len(observations)} Kandidaten "
                          f"({_acc} angenommen, {len(observations) - _acc} verworfen)")
                except Exception as e:
                    print(f"  Beobachtungsprotokoll fehlgeschlagen (unkritisch): {e}")

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
                       last_updated, last_checked, affiliate_url,  -- last_checked NULL bei Neuanlage → Preis-Check greift es beim nächsten Lauf und liefert die History (Chart)
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
                        -- Der /deal-Endpoint liefert nur den avg365-Proxy. Ein bereits
                        -- BELEGTES Tief (aus /product) darf er niemals überschreiben —
                        -- genau das passierte vorher stündlich und machte aus einem
                        -- echten Tief von 22,59 € den Proxy 30,43 €, den der nächste
                        -- Preis-Check dann als „bestätigtes" Tief weiterverwendete.
                        all_time_low    = CASE WHEN products.atl_confirmed
                                               THEN products.all_time_low
                                               ELSE EXCLUDED.all_time_low END,
                        avg_price       = EXCLUDED.avg_price,
                        avg90_price     = EXCLUDED.avg90_price,
                        avg180_price    = EXCLUDED.avg180_price,
                        deal_score      = EXCLUDED.deal_score,
                        rating          = EXCLUDED.rating,
                        reviews         = EXCLUDED.reviews,
                        last_updated    = EXCLUDED.last_updated,
                        affiliate_url   = EXCLUDED.affiliate_url,
                        is_active       = EXCLUDED.is_active,
                        is_backup       = EXCLUDED.is_backup,
                        is_top_pick     = EXCLUDED.is_top_pick,
                        is_fba          = EXCLUDED.is_fba,
                        sales_rank      = EXCLUDED.sales_rank,
                        -- Ein belegtes Allzeittief, das der neue Preis noch hält, darf
                        -- der /deal-Run nicht mit seinem Ø-basierten Tag überschreiben
                        -- (sonst verschwand ein echtes Tief kurz nach dem Deep-Sync).
                        -- Hält der Preis es nicht mehr, gewinnt der neue Tag.
                        tag             = CASE WHEN products.atl_confirmed
                                                AND products.tag = 'Allzeittiefpreis'
                                                AND products.all_time_low > 0
                                                AND EXCLUDED.current_price <= products.all_time_low
                                               THEN products.tag
                                               ELSE EXCLUDED.tag END,
                        score_breakdown = EXCLUDED.score_breakdown
                """,
                    asin, (p["title"] or "")[:200], p["brand"], p["image_url"], p["category"],
                    # all_time_low bei Neuanlage: 0 = unbekannt. Seit 15.08.2026
                    # gibt es hier keinen Proxy mehr — /deal liefert kein Tief,
                    # und ein erfundenes Tief war die Wurzel der drei falschen
                    # „Allzeittiefpreis"-Badges. atl_confirmed bleibt DEFAULT false.
                    p["current_price"], p["original_price"], 0.0, p["avg_price"],
                    # avg180_price bleibt 0, bis /product den echten Wert liefert.
                    p["avg90"] or 0.0, 0.0,
                    p["deal_score"], p["rating"], p["reviews"], True,
                    now, None,   # last_updated=now, last_checked=NULL: Discovery (/deal) liefert KEINE History.
                                 # NULL signalisiert dem stündlichen Preis-Check, dass /product + History noch fehlen.
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

    print(f"  Fertig: {len(active_pool)} aktiv, {len(backup_pool)} Backup")

    # Top Picks über den GESAMTEN aktiven Bestand neu rechnen, nicht nur über
    # die Funde dieses Laufs (Fund 16.08.2026).
    #
    # Die Schleife oben setzt `is_top_pick = i < TOP_PICKS_COUNT` — aber `i`
    # läuft über `active_pool`, und das sind ausschliesslich die Kandidaten
    # DIESES Durchlaufs. Zusammen mit dem `UPDATE products SET is_top_pick=false`
    # weiter oben heisst das: nach jedem Discovery-Lauf sind die Top Picks das,
    # was zufällig gerade hereinkam, unabhängig vom Score.
    #
    # Sichtbar wurde es am 16.08.2026 um 09:05: die Startseite führte mit zwei
    # iPhone-Hüllen (Score 43 und 34), während JBL-Kopfhörer, Bosch-Set und der
    # AOC-Monitor keine Top Picks mehr waren. Repariert hat sich das erst beim
    # Preis-Check um :30 — also fast eine halbe Stunde pro Stunde mit einer
    # falsch sortierten Startseite. Vorher fiel es kaum auf, weil pro Lauf ohnehin
    # nur ein bis zwei Deals hereinkamen; mit dem höheren Zufluss seit MIN_SCORE=18
    # ist es der sichtbarste Fehler auf der Seite.
    #
    # `_recalculate_top_picks()` rechnet rein auf der DB (kein Keepa-Token) und
    # berücksichtigt zusätzlich die Marken-Vielfalt.
    await _recalculate_top_picks()

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
# On-Demand-Chart: Historie beim /preis-Klick live holen + Chart-Eviction
# ---------------------------------------------------------------------------

# Wie viele Tage ein Chart nach dem letzten Aufruf gespeichert bleibt, bevor er
# evictet wird (Stub bleibt, Chart wird bei erneutem Klick neu geholt). Aktive
# Deals sind ausgenommen — die behalten ihren Chart dauerhaft.
CHART_CACHE_DAYS = int(os.getenv("CHART_CACHE_DAYS", "2"))
# Preis gilt als "frisch" (Amazon-Compliance) wenn jünger als so viele Stunden.
PRICE_FRESH_HOURS = int(os.getenv("PRICE_FRESH_HOURS", "24"))


async def fetch_and_store_history(asin: str) -> bool:
    """
    Holt die Preishistorie EINES Produkts live von Keepa (1 Token), speichert sie
    und frischt zugleich die Preis-Eckdaten auf (Amazon-Compliance: Preis < 24h).
    Aufgerufen on-demand beim /preis-Klick, wenn (noch) kein frischer Chart da ist.
    Gibt True zurück, wenn eine echte Historie gespeichert wurde.
    """
    db = await get_pool()
    now = datetime.utcnow()
    keepa_data = await enrich_with_keepa([asin], domain=3)
    kd = keepa_data.get(asin)
    if not kd:
        return False

    hist = kd.get("history") or []
    hist_prices = [pr for pr, _ in hist if pr and pr > 0]
    # Tag MUSS aus derselben history/atl-Momentaufnahme berechnet werden, die
    # unten in price_history geschrieben wird — sonst kann der Badge-Text
    # (z.B. "Bester Preis seit über 1 Jahr") einen Preis behaupten, den der
    # daneben gerenderte Chart widerlegt. Der aktuelle Preis ist dabei KEIN
    # Tief-Kandidat mehr (vorher stand er in der min()-Liste, wodurch das „Tief"
    # nie über ihm lag und der Claim immer durchging).
    atl, atl_ok = resolve_atl(
        kd["current_price"],
        keepa_atl=kd.get("all_time_low") or 0.0,
        history_prices=hist_prices,
        history_span_days=historien_spanne_tage(hist),
    )
    months = best_price_since_months(hist, kd["current_price"])
    tag = determine_tag(kd["current_price"], atl, kd["avg90_price"], kd["avg180_price"],
                        atl_confirmed=atl_ok, months_since_lower=months)
    atl_stored = atl_for_display(atl, kd["current_price"]) if atl_ok else (kd["all_time_low"] or 0.0)

    async with db.acquire() as conn:
        await conn.execute("""
            UPDATE products SET
                current_price = $2, all_time_low = $3, avg_price = $4,
                avg90_price = $5, avg180_price = $6, rating = $7, reviews = $8,
                sales_rank = $9, last_checked = $10, last_viewed = $10,
                image_url = CASE WHEN $11 != '' THEN $11 ELSE image_url END,
                brand     = CASE WHEN $12 != '' THEN $12 ELSE brand END,
                tag       = $13,
                sub_category = CASE WHEN $14 != '' THEN $14 ELSE sub_category END,
                atl_confirmed = $15,
                sub_category2 = CASE WHEN $16 != '' THEN $16 ELSE sub_category2 END
            WHERE asin = $1
        """,
            asin, kd["current_price"], atl_stored, kd["avg_price"],
            kd["avg90_price"], kd["avg180_price"], kd["rating"], kd["reviews"],
            kd["sales_rank"], now, kd["image_url"], (kd.get("brand") or ""),
            tag, kd.get("sub_category") or "", atl_ok,
            kd.get("sub_category2") or "",
        )
        if hist:
            await conn.execute("DELETE FROM price_history WHERE asin=$1", asin)
            await conn.executemany(
                "INSERT INTO price_history (asin, price, timestamp) VALUES ($1,$2,$3)",
                _downsample_daily([(asin, pr, ts) for pr, ts in hist]),
            )
            await conn.execute("UPDATE products SET has_real_history=true WHERE asin=$1", asin)
    return bool(hist)


def _downsample_daily(rows: list) -> list:
    """
    Dünnt (asin, price, timestamp)-Punkte auf max. 1 pro Kalendertag aus (letzter
    Preis des Tages) und kappt auf ~2 Jahre. Visuell identisch zum vollen Chart,
    aber ~3× weniger Speicher — hält Schicht C klein.
    """
    cutoff = datetime.utcnow() - timedelta(days=730)
    by_day: dict = {}
    for asin, price, ts in rows:
        dt = _parse_hist_ts(ts)
        if dt is None or dt < cutoff:
            continue
        by_day[(asin, dt.date())] = (asin, price, ts)  # letzter je Tag gewinnt
    return list(by_day.values())


def _parse_hist_ts(ts) -> Optional[datetime]:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "").split("+")[0])
    except Exception:
        return None


async def evict_stale_charts() -> int:
    """
    Löscht die Preishistorie (Schicht C) von Produkten, die NICHT aktiv sind und
    seit > CHART_CACHE_DAYS nicht mehr angesehen wurden. Der Stub (Name/Eckdaten)
    bleibt — nur der Chart geht, wird bei erneutem Klick neu geholt. So bleibt der
    Chart-Speicher dauerhaft klein (nur Deals + kürzlich Angesehene).
    """
    db = await get_pool()
    cutoff = datetime.utcnow() - timedelta(days=CHART_CACHE_DAYS)
    async with db.acquire() as conn:
        victims = await conn.fetch("""
            SELECT asin FROM products
            WHERE has_real_history = true AND is_active = false
              AND (last_viewed IS NULL OR last_viewed < $1)
        """, cutoff)
        asins = [r["asin"] for r in victims]
        if asins:
            await conn.execute("DELETE FROM price_history WHERE asin = ANY($1::text[])", asins)
            await conn.execute(
                "UPDATE products SET has_real_history = false WHERE asin = ANY($1::text[])", asins)
    print(f"[{datetime.utcnow().isoformat()}] Chart-Eviction: {len(asins)} Charts gelöscht "
          f"(nicht aktiv, > {CHART_CACHE_DAYS} Tage nicht angesehen).")
    return len(asins)


# ---------------------------------------------------------------------------
# Bestseller-Seeding: Katalog mit Top-Produkten je Kategorie füllen
# ---------------------------------------------------------------------------


async def seed_bestsellers(max_tokens: int = 6000, max_per_cat: int = 400,
                            category_offset: int = 0) -> dict:
    """
    Füllt den Katalog mit STUBS (Name+Eckdaten, KEINE Historie — Schicht C kommt
    erst on-demand beim /preis-Klick, siehe fetch_and_store_history) aus den
    Bestsellern aller Kategorie-Knoten in ROOTCAT_MAP plus deren direkten
    Unterknoten (via _expanded_seed_nodes, ~300-500 Knoten).

    Für jede Kategorie:
    1. Bestseller-ASIN-Liste holen (1 Token/Kategorie via /bestsellers)
    2. Bereits im Katalog vorhandene ASINs herausfiltern (keine Doppel-Kosten)
    3. Verbleibende neue ASINs anreichern (1 Token/ASIN via /product)
    4. classify_category + is_catalog_quality durchlaufen — Ramsch fliegt vorher raus
    5. Neue Einträge als Stub anlegen (is_active=false, has_real_history=false)
       mit kategoriebezogenem Affiliate-Tag.

    Hartes `max_tokens`-Limit: bricht Kategorienzuweisung sauber ab, sobald das
    Tagesbudget erreicht ist. Keine schleichenden Überziehungen.

    `category_offset` rotiert die Startposition in der Seed-Knoten-Liste —
    ohne Rotation würden bei knappem Stunden-Budget immer dieselben ersten
    Kategorien bedient und spätere (z.B. Sport & Freizeit) nie erreicht. Der
    stündliche Job dreht den Offset weiter, der manuelle Admin-Push (großes
    Budget, deckt meist alles ab) startet bei 0.
    """
    from scoring import is_catalog_quality  # lokal um Zirkularität zu vermeiden
    print(f"[{datetime.utcnow().isoformat()}] Bestseller-Seeding startet "
          f"(max_tokens={max_tokens}, max_per_cat={max_per_cat}) …")
    db = await get_pool()
    now = datetime.utcnow()
    tokens_used = 0
    stats: dict[str, dict] = {}

    # Quelle: ALLE ROOTCAT_MAP-Knoten PLUS deren direkte Unterknoten (siehe
    # _expanded_seed_nodes) — Root-Bestseller-Listen sind Zubehör-dominiert,
    # echte Produkte (iPhone, TVs, …) stehen in den Unterknoten-Listen.
    # Die endgültige Kategorie je Produkt entscheidet ohnehin
    # classify_category(title, root_cat) — der Knoten hier ist nur die Bezugsquelle.
    # Rotiert um category_offset (siehe Docstring), damit bei knappem Budget nicht
    # immer dieselben ersten Kategorien bedient werden.
    async with httpx.AsyncClient(timeout=45) as client:
        cat_items, discovery_cost = await _expanded_seed_nodes(client)
    tokens_used += discovery_cost
    if cat_items:
        off = category_offset % len(cat_items)
        cat_items = cat_items[off:] + cat_items[:off]
    for cat_id, cat_name in cat_items:
        label = f"{cat_name}#{cat_id}"
        async with httpx.AsyncClient(timeout=45) as client:
            if tokens_used >= max_tokens:
                stats[label] = {"skipped": "budget"}
                continue

            asins, cost = await fetch_keepa_bestsellers(cat_id, domain=3, client=client)
            tokens_used += cost
            if not asins:
                stats[label] = {"tokens": cost, "fetched": 0}
                continue
            asins = asins[:max_per_cat]

            async with db.acquire() as conn:
                existing = {r["asin"] for r in await conn.fetch(
                    "SELECT asin FROM products WHERE asin = ANY($1::text[])", asins
                )}
            new_asins = [a for a in asins if a not in existing]

            if not new_asins:
                stats[label] = {"tokens": cost, "fetched": len(asins), "new": 0}
                continue

            # Enrichment-Budget prüfen, nötigenfalls kürzen
            remaining = max_tokens - tokens_used
            if len(new_asins) > remaining:
                new_asins = new_asins[:remaining]

            keepa_data = await enrich_with_keepa(new_asins, domain=3, client=client)
            # Grobe Kostenschätzung (1 Token/ASIN inkl. History)
            tokens_used += len(new_asins)

            added = 0
            skipped_junk = 0
            skipped_quality = 0
            skipped_cheap = 0
            async with db.acquire() as conn:
                for asin, kd in keepa_data.items():
                    title = kd.get("title") or ""
                    cls_cat = classify_category(title, kd.get("root_cat") or 0)
                    if not cls_cat:
                        skipped_junk += 1
                        continue
                    if not is_catalog_quality(
                        kd["rating"] or 0, kd["reviews"] or 0,
                        kd.get("brand") or "", title
                    ):
                        skipped_quality += 1
                        continue
                    cat_min_catalog = CATEGORY_MIN_PRICE.get(cls_cat, MIN_PRICE) * CATALOG_MIN_PRICE_MULTIPLIER
                    if (kd["current_price"] or 0) < cat_min_catalog:
                        skipped_cheap += 1
                        continue

                    aff_tag = _affiliate_tag_for(cls_cat)
                    hist = kd.get("history") or []
                    hist_prices = [pr for pr, _ in hist if pr and pr > 0]
                    # Belegtes Tief oder 0 (= unbekannt) — nie der aktuelle Preis.
                    atl_real, atl_ok = resolve_atl(
                        kd["current_price"],
                        keepa_atl=kd.get("all_time_low") or 0.0,
                        history_prices=hist_prices,
                        history_span_days=historien_spanne_tage(hist),
                    )
                    atl = atl_for_display(atl_real, kd["current_price"]) if atl_ok else 0.0

                    # STUB-only: Name + Eckdaten speichern, KEINE Preishistorie
                    # (Schicht C). Der Chart wird erst on-demand beim ersten /preis-
                    # Klick live geholt (has_real_history=false). Spart Speicher →
                    # Katalog kann auf ~100k wachsen ohne Supabase-Free zu sprengen.
                    await conn.execute("""
                        INSERT INTO products
                          (asin, name, brand, image_url, category,
                           current_price, original_price, all_time_low, avg_price,
                           avg90_price, avg180_price, deal_score, rating, reviews, prime,
                           last_updated, last_checked, affiliate_url,
                           is_active, is_backup, is_top_pick, is_fba,
                           sales_rank, tag, score_breakdown, first_seen, has_real_history,
                           sub_category, atl_confirmed, sub_category2)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                                $16,$17,$18,false,false,false,$19,$20,'','',$16,false,$21,$22,$23)
                        ON CONFLICT (asin) DO NOTHING
                    """,
                        asin, (title or "Produkt")[:200], kd.get("brand") or "",
                        kd["image_url"], cls_cat,
                        kd["current_price"], kd["original_price"], atl, kd["avg_price"],
                        kd["avg90_price"] or 0.0, kd["avg180_price"] or 0.0,
                        0, kd["rating"], kd["reviews"], True,
                        now, now, f"https://www.amazon.de/dp/{asin}?tag={aff_tag}",
                        kd.get("is_fba") or False, kd["sales_rank"] or 0,
                        kd.get("sub_category") or "", atl_ok,
                        kd.get("sub_category2") or "",
                    )
                    added += 1

            stats[label] = {
                "tokens": cost + len(new_asins),
                "fetched": len(asins),
                "new_candidates": len(new_asins),
                "added": added,
                "skipped_junk": skipped_junk,
                "skipped_quality": skipped_quality,
                "skipped_cheap": skipped_cheap,
            }
            print(f"  [ok] {label}: +{added} neu (junk:{skipped_junk} low-quality:{skipped_quality} "
                  f"cheap:{skipped_cheap}) - Tokens: {tokens_used}/{max_tokens}")

    print(f"[{datetime.utcnow().isoformat()}] Bestseller-Seeding fertig. "
          f"Tokens gesamt: {tokens_used}")
    return {"tokens_used": tokens_used, "categories": stats}


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
            "SELECT asin, category, name FROM products WHERE is_active=true "
            "ORDER BY deal_score DESC LIMIT $1",
            DEEPSYNC_LIMIT,
        )
    asins = [r["asin"] for r in rows]
    # Kategorie + Titel je ASIN für ein korrekt gewichtetes Re-Scoring (sonst
    # würde der Deep-Sync die Kategorie-Gewichtung/Junk-Abzüge überschreiben).
    meta_by_asin = {r["asin"]: (r["category"] or "Sonstiges", r["name"] or "") for r in rows}
    if not asins:
        print("  Keine Deals für Deep-Sync gefunden.")
        return

    # History steckt im Basis-Token → wird für alle mitgeholt (kein Sparzwang mehr).
    print(f"  Deep-Sync für {len(asins)} ASINs (History inklusive) …")
    keepa_data = await enrich_with_keepa(asins, domain=3)
    now        = datetime.utcnow()

    async with db.acquire() as conn:
        for asin, kd in keepa_data.items():
            # Echtes Allzeittief konsistent zur angezeigten Historie: Keepa-ATL und
            # Minimum der tatsächlichen Preishistorie — der aktuelle Preis ist KEIN
            # Kandidat (er war es früher, wodurch das Tief nie über ihm lag und
            # "Allzeittiefpreis" immer zutraf).
            hist_prices = [pr for pr, _ in (kd.get("history") or []) if pr and pr > 0]
            atl_real, atl_ok = resolve_atl(
                kd["current_price"],
                keepa_atl=kd.get("all_time_low") or 0.0,
                history_prices=hist_prices,
                history_span_days=historien_spanne_tage(kd.get("history") or []),
            )
            # In die DB/Anzeige geht der geklemmte Wert (Tief nie über aktuellem
            # Preis); in die Tag-Entscheidung unten der unbeschnittene atl_real.
            # Ohne Beleg bleibt der gespeicherte Wert unangetastet (SQL-CASE unten):
            # `all_time_low` dient auch als Langfrist-Anker für passes_hard_filters()
            # und darf dort nicht auf 0 fallen — nur `atl_confirmed` entscheidet,
            # ob daraus ein Tief-CLAIM werden darf.
            kd["all_time_low"] = atl_for_display(atl_real, kd["current_price"]) if atl_ok else 0.0

            cat_db, title_db = meta_by_asin.get(asin, ("Sonstiges", ""))
            score, breakdown = calculate_deal_score(
                kd["current_price"], kd["avg90_price"], kd["all_time_low"],
                kd["sales_rank"], cat_db,
                kd["rating"], kd["reviews"],
                price_updated=now,
                title=title_db,
            )
            # Echte History → konkretes Urteil "Bester Preis seit X Monaten".
            # atl_confirmed kommt aus resolve_atl(), nicht mehr pauschal True:
            # auch /product liefert nicht für jedes Produkt ein stats.atl, und
            # ohne Beleg darf kein Tief-Claim entstehen.
            months = best_price_since_months(kd.get("history") or [], kd["current_price"])
            tag = determine_tag(kd["current_price"], atl_real,
                                kd["avg90_price"], kd["avg180_price"],
                                atl_confirmed=atl_ok, months_since_lower=months)

            await conn.execute("""
                UPDATE products SET
                    current_price   = $2,
                    original_price  = $3,
                    all_time_low    = CASE WHEN $19 THEN $4 ELSE all_time_low END,
                    atl_confirmed   = $19,
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
                    brand           = CASE WHEN $17 != '' THEN $17 ELSE brand END,
                    sub_category    = CASE WHEN $18 != '' THEN $18 ELSE sub_category END,
                    sub_category2   = CASE WHEN $20 != '' THEN $20 ELSE sub_category2 END
                WHERE asin = $1
            """,
                asin,
                kd["current_price"], kd["original_price"], kd["all_time_low"],
                kd["avg_price"], kd["avg90_price"], kd["avg180_price"],
                kd["rating"], kd["reviews"], kd["sales_rank"], kd["is_fba"],
                score, tag, breakdown, now, kd["image_url"], (kd.get("brand") or ""),
                kd.get("sub_category") or "", atl_ok,
                kd.get("sub_category2") or "",
            )

            # Echte Preishistorie IMMER frisch setzen: alte (evtl. simulierte)
            # Punkte löschen, echte Keepa-Serie einspielen, has_real_history setzen.
            # Erst ab jetzt wird für dieses Produkt überhaupt ein Chart gezeigt.
            if kd["history"]:
                recent = kd["history"][-2000:]  # volle History (Chart-Default zeigt 365 Tage)
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
