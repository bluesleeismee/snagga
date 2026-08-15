"""
Kategorie-Tabelle — die EINE Quelle dafür, was snagga zeigt und was nicht.

Warum es diese Datei in dieser Form gibt (David, 15.08.2026)
------------------------------------------------------------
Bis heute lagen die Kategorie-Entscheidungen an vier Stellen verteilt und
widersprachen sich: `INCLUDE_CAT_IDS` (was bei Keepa abgefragt wird),
`ROOTCAT_MAP` (wohin Treffer einsortiert werden), `ELECTRONICS_CAT_IDS` (eine
Zusatzabfrage) und `SUBCATEGORY_ROLE` (Kern/Zubehör). Keine der vier war
vollständig, und niemand konnte sagen, warum ein bestimmtes Produkt im Regal
stand. Am 15.08.2026 waren noch 29 Deals aktiv, darunter eine Einlagesohle.

Alles Kategorie-Wissen steht deshalb ab jetzt hier.

Die drei Rollen
---------------
Bis heute gab es nur KERN und ZUBEHOER, und alles Unbekannte galt als KERN,
"damit eine Pflegelücke nichts aussperrt". Das war die eigentliche Lücke:
„Wohnaccessoires & Deko" (818 Katalogprodukte, durchgehend No-Name-Teppiche und
Bilderrahmen) wurde dadurch nur quotiert statt ausgeschlossen — es konkurrierte
also weiter um Plätze, statt zu verschwinden.

  KERN      Wird bei Keepa aktiv abgefragt. Das ist die Ware, für die snagga da
            ist. Nur hier wird gesucht.
  ZUBEHOER  Darf vorkommen, aber höchstens bis MAX_ZUBEHOER_ANTEIL der aktiven
            Deals einer Oberkategorie. Wird nicht aktiv gesucht.
  RAUS      Erscheint nie. Weder als Deal noch als /preis-Seite.

Unbekannte Unterkategorien gelten jetzt als ZUBEHOER, nicht mehr als KERN: sie
werden ohnehin nicht aktiv gesucht, dürfen also auftauchen — aber gedeckelt.

Herkunft der Einordnung
-----------------------
Die Namen stammen aus Keepas eigenem Kategoriebaum bzw. aus der Messung über
`/debug/subcategories` (echte `sub_category`-Werte des Katalogs), nicht aus
Vermutungen. Acht Zweifelsfälle wurden am 15.08.2026 zusätzlich über
`/debug/subcategory-sample` entschieden — also anhand der tatsächlichen
Produkttitel, nicht anhand des Median-Preises.

Der Median-Preis allein führt nämlich in die Irre: „Handys & Zubehör" (Median
33 €) enthält an der Spitze Galaxy S25 Ultra und iPhone Air, „Haarpflege &
Styling" (Median 30 €) enthält ghd- und Parlux-Geräte bis 256 €. In beiden
Fällen liegt eine kleine hochwertige Spitze unter einem breiten Zubehör-Sockel.
Solche Töpfe gehören auf KERN — die Kleinteile darunter filtert der Mindestpreis
und die Mindestersparnis (scoring.py), nicht die Kategorie.

Vollständige Begründung je Zeile: KATEGORIEN_NEU.md im Projektordner.
"""
from __future__ import annotations

import os

KERN      = "kern"
ZUBEHOER  = "zubehoer"
RAUS      = "raus"
UNBEKANNT = "unbekannt"


# ---------------------------------------------------------------------------
# Oberkategorien → Unterkategorie (klein) → Rolle
# ---------------------------------------------------------------------------
# Elf Oberkategorien. Gestrichen gegenüber früher: Auto & Motorrad (Nischen-
# Ersatzteile), Software (keine belastbare Preishistorie), Kosmetik (dupliziert
# sechs von neun Unterkategorien aus Drogerie & Körperpflege und enthält keine
# Geräte), Beleuchtung (Unterkategorien tauchen ohnehin unter Küche/Haushalt auf
# und stehen dort auf ZUBEHOER/RAUS) sowie Kamera & Foto — letzteres existiert
# bei Keepa gar nicht als Root-Kategorie, sondern hängt unter Elektronik & Foto.
# Die alte Snagga-Kategorie "Kamera & Foto" konnte deshalb nie befüllt werden.
#
# Garten ist bewusst KEINE eigene Oberkategorie, der Keepa-Root 10925031 bleibt
# aber in der Abfrage und wird nach Baumarkt einsortiert: Rasenmäher,
# Bewässerungsgeräte und Gartenmöbel hängen bei Amazon dort, nicht unter
# Baumarkt. Was davon sichtbar wird, steuert allein die Tabelle unten.

KATEGORIEN: dict[str, dict[str, str]] = {

    "Baumarkt": {
        "elektro- & handwerkzeuge":                     KERN,
        "rasenmäher & elektrische gartenwerkzeuge":     KERN,
        "garten- & bewässerungsgeräte":                 KERN,
        "grills & zubehör":                             KERN,
        "sicherheitstechnik":                           KERN,
        "küchen- & badarmaturen":                       KERN,
        "gartenmöbel & zubehör":                        KERN,
        "pools, gartensaunas & badewannen mit sprudelfunktion": KERN,
        "heizstrahler & feuerstellen":                  KERN,
        "gartenhäuser & aufbewahrung":                  KERN,
        "thermometer & wetterstationen":                KERN,
        "elektroinstallation":                          ZUBEHOER,
        "klempnerarbeiten":                             ZUBEHOER,
        "teiche & zubehör":                             ZUBEHOER,
        "gartenarbeit":                                 ZUBEHOER,
        # Eisenwaren (167) und Baubedarf (328) sind die zwei grössten
        # Kleinteil-Töpfe der Kategorie: Schrauben, Beschläge, Dübel.
        "eisenwaren":                                   RAUS,
        "baubedarf":                                    RAUS,
        "malerbedarf, werkzeuge & tapeten":             RAUS,
        # Median 110 € täuscht: 13 von 15 Treffern sind Kunstrasen-Meterware
        # DESSELBEN Anbieters, alle mit Verkaufsrang 12188 — Varianten einer
        # Ware, die als eigene ASINs im Katalog liegen.
        "gartendeko":                                   RAUS,
        "blumen & pflanzen":                            RAUS,
        "lagerung & heimorganisation":                  RAUS,
        "wildtiere":                                    RAUS,
        "hunde":                                        RAUS,
        "schuh-, schmuck- & uhren-accessoires":         RAUS,
        "möbel":                                        RAUS,   # gehört zu KHW
    },

    "Computer & Zubehör": {
        "laptops":                            KERN,
        "desktop-pcs":                        KERN,
        "tablet pcs":                         KERN,
        "monitore":                           KERN,
        "netzwerk":                           KERN,
        "komponenten & ersatzteile":          KERN,
        "datenspeicher":                      KERN,
        "drucker & zubehör":                  KERN,
        "scanner & zubehör":                  KERN,
        "server":                             KERN,
        "barebones":                          KERN,
        # Keepa-Eigenname, hängt auch unter Games. Enthält KEINE Konsolen,
        # sondern Gaming-Hardware: Thrustmaster-Rennlenkräder (440 €), Astro
        # A50 X (343 €), Razer/Corsair/SteelSeries/ASUS-ROG-Tastaturen und
        # -Mäuse (150–310 €), PlayStation Portal, Seagate Xbox-Speicherkarte.
        "plattformen":                        KERN,
        "computer-zubehör":                   ZUBEHOER,
        "mäuse, tastaturen & eingabegeräte":  ZUBEHOER,
        "pc-gaming-zubehör":                  ZUBEHOER,
        "lcd-schreibtafeln":                  RAUS,
    },

    "Drogerie & Körperpflege": {
        # Die Geräte-Töpfe: Oral-B und Sonicare unter Mund- & Zahnpflege,
        # Braun und Philips unter Rasur, Beurer und Omron unter Medizinische
        # Geräte, ghd und Parlux unter Haarpflege.
        "mund- & zahnpflege":                           KERN,
        "rasur & enthaarung":                           KERN,
        "medizinische geräte & verbrauchsmaterialien":  KERN,
        "haarpflege & styling":                         KERN,
        "wellness":                                     ZUBEHOER,
        "maniküre & pediküre":                          ZUBEHOER,
        "düfte":                                        ZUBEHOER,
        # Ab hier Verbrauchsware — kein Preisverlauf, der einen Kaufzeitpunkt
        # begründen würde.
        "hautpflege":                                   RAUS,
        "make-up":                                      RAUS,
        "baden & körperpflege":                         RAUS,
        "vitamine, mineralien & ergänzungsmittel":      RAUS,
        "nahrungsergänzung":                            RAUS,
        "medizin & erste hilfe":                        RAUS,
        "mobilitätshilfen & zubehör":                   RAUS,
        "haushaltswaren":                               RAUS,
        "zubehör":                                      RAUS,
        "kontaktlinsen & brillen":                      RAUS,
        "intime pflege & hygiene":                      RAUS,
        "baby- & kinderpflege":                         RAUS,
        "erotik":                                       RAUS,
    },

    "Elektro-Großgeräte": {
        "waschmaschinen & trockner":                        KERN,
        "kühlschränke, gefrierschränke & eiswürfelbereiter": KERN,
        "geschirrspüler":                                   KERN,
        "backöfen, kochfelder & dunstabzugshauben":         KERN,
        "zubehör":                                          ZUBEHOER,
    },

    "Elektronik & Foto": {
        "tragbare technologie":                 KERN,
        "tragbare geräte":                      KERN,
        "hifi & audio":                         KERN,
        "kopfhörer & zubehör":                  KERN,
        "auto- & fahrzeugelektronik":           KERN,
        "kamera & foto":                        KERN,
        "festnetztelefone, voip & zubehör":     KERN,
        "navigation, gps & zubehör":            KERN,
        "fernseher & heimkino":                 KERN,
        "funkgeräte & zubehör":                 KERN,
        "ebook-reader & -zubehör":              KERN,
        # Median 33 €, aber an der Spitze Galaxy S25 Ultra (1469 €), iPhone Air
        # (799 €), Pixel 10a. Zubehör beginnt erst unter ~100 € und wird vom
        # Mindestpreis/der Mindestersparnis abgefangen, nicht von der Quote.
        "handys & zubehör":                     KERN,
        "netzkabel, verteiler & adapter":       ZUBEHOER,
        "batterien, akkus & zubehör":           ZUBEHOER,
        "elektronische zigaretten, shishas & zubehör": RAUS,
    },

    "Games": {
        "plattformen": KERN,
    },

    "Gewerbe, Industrie & Wissenschaft": {
        # Aufgenommen wegen 3D-Druck. Von 23 Unterkategorien sind 5 brauchbar,
        # der Rest ist B2B-Verbrauchsmaterial — genau die Ecke, aus der der
        # "Leistenbruchgürtel" kam.
        "3d-druck & digitalisierung":                   KERN,
        "test & messung":                               KERN,
        "elektrowerkzeuge & handwerkzeuge":             KERN,
        "solar- & windenergie":                         KERN,
        "systemgastronomieausrüstung & -zubehör":       KERN,
        "schneidwerkzeuge":                             ZUBEHOER,
        "elektroinstallation":                          ZUBEHOER,
        "landwirtschaftliche geräte & zubehör":         ZUBEHOER,
        "antriebstechnikprodukte":                      RAUS,
        "hydraulik & pneumatik":                        RAUS,
        "filtration":                                   RAUS,
        "schleifmittel & veredlungsprodukte":           RAUS,
        "materialtransport, ladungssicherung & zubehör": RAUS,
        "versandverpackungen & kartonagen":             RAUS,
        "sanitärbedarf & reinigungsmittel":             RAUS,
        "labor- & wissenschaftlich genutzte produkte":  RAUS,
        "profi-medizinbedarf":                          RAUS,
        "dentalbedarf":                                 RAUS,
        "einzelhandelseinrichtungen & ausrüstungen":    RAUS,
        "rohstoffe":                                    RAUS,
        "bildungs- & schulbedarf":                      RAUS,
        "produkte für arbeitsschutz & sicherheit":      RAUS,
        "specialty stores":                             RAUS,
    },

    "Küche, Haushalt & Wohnen": {
        "haushaltsreiniger & staubsauger":      KERN,
        "haushaltsgroßgeräte":                  KERN,
        "heizen & kühlen":                      KERN,
        "elektrische küchengeräte":             KERN,
        # Höhenverstellbare Schreibtische (FLEXISPOT, Desktronic),
        # Esszimmerstuhl-Sets, Matratzen — 280 bis 1160 €.
        "möbel":                                KERN,
        "waschen & bügeln":                     KERN,
        # Le Creuset Bräter, ZWILLING Messer, RÖSLE/Tefal Topfsets,
        # De'Longhi Vollautomat, Ninja.
        "küche, kochen & backen":               KERN,
        "innenbeleuchtung":                     ZUBEHOER,
        "außenbeleuchtung":                     ZUBEHOER,
        "bettwaren & bettwäsche":               ZUBEHOER,
        "badausstattung":                       ZUBEHOER,
        # 818 Katalogprodukte, selbst an der Preisspitze No-Name-Teppiche,
        # Bilderrahmen, Kunstblumen, Spiegel. Der grösste Einzeltopf der
        # Datenbank und der Hauptgrund, warum die Kategorie nach Deko aussah.
        "wohnaccessoires & deko":               RAUS,
        "basteln, malen & handarbeiten":        RAUS,
        "bilder, poster, kunstdrucke & skulpturen": RAUS,
        "aufbewahrung & organisation":          RAUS,
        "abfall & recycling":                   RAUS,
        "leuchtmittel":                         RAUS,
        "lichterketten":                        RAUS,
        "bad-beleuchtung":                      RAUS,
        "systemgastronomieausrüstung & -zubehör": RAUS,
    },

    "Musikinstrumente & DJ-Equipment": {
        "piano & keyboard":             KERN,
        "recording-equipment":          KERN,
        "schlagzeug & percussion":      KERN,
        "pa- & bühnentechnik":          KERN,
        "blasinstrumente":              KERN,
        "mikrofone":                    KERN,
        "gitarren, bässe & sets":       KERN,
        "dj- & vj-equipment":           KERN,
        "streich- & zupfinstrumente":   KERN,
        "karaoke":                      ZUBEHOER,
        "musizier-zubehör":             ZUBEHOER,
    },

    "Spielzeug": {
        # Beste Neuaufnahme des Umbaus: LEGO und Playmobil unter Bau- &
        # Konstruktionsspielzeug, Ravensburger und Kosmos unter Spiele/Puzzles/
        # Experimentieren, Carrera und Bruder unter Fahrzeuge. Feste Marken,
        # hohe Preise, ausgeprägte Preiszyklen.
        "bau- & konstruktionsspielzeug":        KERN,
        "spielzeugfiguren":                     KERN,
        "fahrzeuge":                            KERN,
        "elektronisches spielzeug":             KERN,
        "ferngesteuerte spielzeuge & zubehör":  KERN,
        "experimentieren & forschen":           KERN,
        "spiele":                               KERN,
        "puzzles":                              KERN,
        "puppen & zubehör":                     KERN,
        "plüsch-spielzeug":                     ZUBEHOER,
        "baby- & kleinkindspielzeug":           ZUBEHOER,
        "sammelspielzeuge":                     ZUBEHOER,
        # ACHTUNG beim Lesen: heissen wie echte Oberkategorien, meinen hier
        # aber Kinderspielzeug. Die Zuordnung erfolgt immer INNERHALB der
        # Oberkategorie, deshalb ungefährlich.
        "musikinstrumente":                     ZUBEHOER,
        "sport & outdoor":                      ZUBEHOER,
        "hobbys":                               ZUBEHOER,
        "kunst & handwerk":                     RAUS,
        "verkleiden & kinderrollenspiele":      RAUS,
        "puppen- & kasperletheater":            RAUS,
        "party & dekoration":                   RAUS,
        "party- & scherzartikel":               RAUS,
        "schulbedarf":                          RAUS,
        "adventskalender":                      RAUS,
    },

    "Sport & Freizeit": {
        # "Sport" ist mit 909 Produkten der grösste Topf und vom Namen her
        # nichtssagend — die Titel-Stichprobe zeigt echte Kernware: SUP-Boards,
        # Trampoline, Kajaks, Airtrack-Matten, ABUS-Helme, SUUNTO-Tauchcomputer,
        # Garmin-Echolot.
        "sport":                            KERN,
        "fitness":                          KERN,
        "sport & outdoor aktivitäten":      KERN,
        "sportelektronik":                  KERN,
        "jagen & angeln":                   ZUBEHOER,
        "sport & outdoor freizeitzubehör":  ZUBEHOER,
        "gepäck & reiseausrüstung":         ZUBEHOER,
        # Median 22 €, teuerstes Produkt 30 €. Hier sass die Einlagesohle, die
        # den ganzen Umbau ausgelöst hat. Eine Unterkategorie, die strukturell
        # nichts liefern kann, was snagga zeigen will.
        "sportmedizin":                     RAUS,
        "sportfanshop":                     RAUS,
        "sportbekleidung":                  RAUS,
        "kleidung für spezielle anlässe":   RAUS,
        "pokale, medaillen & auszeichnungen": RAUS,
    },
}


# Höchstanteil ZUBEHOER an den aktiven Deals je Oberkategorie.
# Fehlt ein Eintrag, gilt für diese Kategorie keine Grenze.
#
# Warum eine Quote und kein Verbot: sie korrigiert sich selbst. Kommt an einem
# Tag kein guter Laptop-Deal, bleibt der Platz knapper besetzt, statt mit dem
# nächsten Kabel gefüllt zu werden.
MAX_ZUBEHOER_ANTEIL: dict[str, float] = {
    "Baumarkt":                          0.40,
    "Computer & Zubehör":                0.40,
    "Drogerie & Körperpflege":           0.40,
    "Elektro-Großgeräte":                0.40,
    "Elektronik & Foto":                 0.40,
    "Gewerbe, Industrie & Wissenschaft": 0.40,
    "Küche, Haushalt & Wohnen":          0.40,
    "Musikinstrumente & DJ-Equipment":   0.40,
    "Spielzeug":                         0.40,
    "Sport & Freizeit":                  0.40,
}

# Notausschalter ohne Deploy, falls die Quote im Betrieb zu viel wegschneidet.
QUOTA_AKTIV = os.getenv("SORTIMENT_QUOTA_AKTIV", "1") not in ("0", "false", "False")

# Notausschalter für die RAUS-Regel, getrennt von der Quote: die eine kann zu
# streng sein, ohne dass die andere es ist.
RAUS_AKTIV = os.getenv("SORTIMENT_RAUS_AKTIV", "1") not in ("0", "false", "False")


# ---------------------------------------------------------------------------
# Abfragen
# ---------------------------------------------------------------------------

def rolle(category: str, sub_category: str) -> str:
    """
    Rolle einer Unterkategorie innerhalb ihrer Oberkategorie.

    Unbekanntes gilt als ZUBEHOER (bis 15.08.2026: als Kern). Begründung: aktiv
    gesucht wird ohnehin nur in KERN-Knoten, unbekannte Ware kommt also nur
    beiläufig herein. Sie darf erscheinen, aber gedeckelt — nicht unbegrenzt wie
    bisher.

    Ist die ganze Oberkategorie unbekannt, bleibt es bei UNBEKANNT; solche
    Produkte gehören nicht zum Sortiment und werden vom Aufrufer verworfen.

    WICHTIG — leere `sub_category` ergibt UNBEKANNT, nicht ZUBEHOER: Keepas
    /deal-Endpoint liefert die Unterkategorie nicht, sie kommt erst mit der
    /product-Anreicherung. Ein frisch entdeckter Deal hat das Feld also noch
    leer. Würde er als Zubehör gelten, räumte ihn die Quote weg, bevor er
    überhaupt eingeordnet werden konnte — und je knapper das Regal, desto mehr
    davon (genau die Abwärtsspirale vom 15.08.2026: 68 aktive Deals fielen
    innerhalb einer Stunde auf 49).
    """
    tabelle = KATEGORIEN.get(category or "")
    if not tabelle:
        return UNBEKANNT
    sub = (sub_category or "").strip().lower()
    if not sub:
        return UNBEKANNT
    return tabelle.get(sub, ZUBEHOER)


def ist_raus(category: str, sub_category: str) -> bool:
    """
    True, wenn diese Unterkategorie nie erscheinen soll.

    Greift bewusst NICHT bei leerer `sub_category`: die kommt aus Keepas
    /product und fehlt bei frisch entdeckten Deals noch. Ein Produkt wegen einer
    noch nicht geladenen Angabe auszuschliessen, würde die Discovery leerlaufen
    lassen — die Prüfung wiederholt sich beim nächsten Preis-Check ohnehin.
    """
    if not RAUS_AKTIV or not (sub_category or "").strip():
        return False
    return rolle(category, sub_category) == RAUS


def zuviel_zubehoer(category: str, n_zubehoer: int, n_gesamt: int) -> int:
    """
    Wie viele ZUBEHOER-Deals liegen über der Quote? 0 = alles im Rahmen.

    Gerechnet wird gegen die Zahl der NICHT-Zubehör-Deals, nicht gegen die
    Gesamtzahl (Korrektur David, 15.08.2026).

    Beide Formeln landen am selben Endzustand — die alte kommt nur nicht in
    einem Schritt dorthin:

        alt:  10 aktiv / 5 Zubehör → 1 raus → 9/4 → 1 raus → 8/3 → Stopp
        neu:  10 aktiv / 5 Zubehör → 2 raus → 8/3 → Stopp

    Der Unterschied ist die Rückkopplung. Bei der alten Formel senkte jede
    Deaktivierung die Gesamtzahl und damit die erlaubte Menge, was im nächsten
    Lauf die nächste Deaktivierung auslöste. Zwischen zwei Läufen rücken aber
    Backups nach (_promote_backups_simple) — die Kategorie kam damit nie zur
    Ruhe, sondern deaktivierte und ersetzte stündlich weiter. Genau dieses
    Zappeln war am 15.08.2026 zu sehen, als die aktiven Deals innerhalb einer
    Stunde von 68 auf 49 fielen.

    Gegen die Kernmenge gerechnet ist die Grenze stabil: sie ändert sich nicht,
    wenn Zubehör verschwindet. Ein Durchlauf stellt die Quote exakt her, der
    nächste findet nichts mehr zu tun.
    """
    if not QUOTA_AKTIV or n_gesamt <= 0:
        return 0
    grenze = MAX_ZUBEHOER_ANTEIL.get(category or "")
    if grenze is None or grenze >= 1.0:
        return 0
    n_kern = max(0, n_gesamt - n_zubehoer)
    erlaubt = int(n_kern * grenze / (1.0 - grenze))
    return max(0, n_zubehoer - erlaubt)


def kern_namen(category: str) -> set[str]:
    """
    Klein geschriebene Namen der KERN-Unterkategorien einer Oberkategorie.
    Das ist das Suchfenster der Discovery.
    """
    tabelle = KATEGORIEN.get(category or "") or {}
    return {name for name, r in tabelle.items() if r == KERN}


def raus_namen(category: str) -> set[str]:
    """Klein geschriebene Namen der RAUS-Unterkategorien einer Oberkategorie."""
    tabelle = KATEGORIEN.get(category or "") or {}
    return {name for name, r in tabelle.items() if r == RAUS}


def oberkategorien() -> list[str]:
    """Alle Snagga-Oberkategorien in fester Reihenfolge."""
    return list(KATEGORIEN)


def ist_konfiguriert() -> bool:
    """True, sobald mindestens eine Kategorie eingeordnet UND begrenzt ist."""
    return bool(KATEGORIEN and MAX_ZUBEHOER_ANTEIL)


def hat_kern_namen() -> bool:
    """True, wenn für mindestens eine Oberkategorie KERN-Knoten definiert sind."""
    return any(kern_namen(c) for c in KATEGORIEN)


# Rückwärtskompatibilität: der alte Name der Tabelle. Bestehende Aufrufer
# (scraper.py, main.py) laufen damit unverändert weiter, bis sie umgestellt sind.
SUBCATEGORY_ROLE = KATEGORIEN
