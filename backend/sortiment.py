"""
Kernsortiment vs. Zubehör — damit eine Kategorie zeigt, was ihr Name verspricht.

Das Problem (David, 11.08.2026)
-------------------------------
In „Computer & Zubehör" standen fast nur Rucksäcke, Tintenpatronen und Kabel
statt PCs, Laptops, Monitoren; in „Küche, Haushalt & Wohnen" Bürostuhlrollen und
Gewürzgläser statt Küchengeräten, Messern, Staubsaugern.

Das ist keine Nachlässigkeit im Filter, sondern strukturell: die Oberkategorie
stammt aus Keepas oberster Ebene, und dort liegt ein Laptop im selben Topf wie
ein USB-Kabel. Zubehör ist millionenfach häufiger, wird häufiger rabattiert und
hat bessere Verkaufsränge — der Filter kann also gar nicht anders, als
überwiegend Zubehör zu liefern. Gegen so etwas hilft keine weitere Stichwortliste
(`specificity_penalty`): für jedes gesperrte Wort kommt ein neues Kleinteil nach.

Der Ansatz
----------
Keepa liefert die zweite Kategorieebene mit, sie steht in `products.sub_category`.
Darüber lässt sich pro Oberkategorie ein **Kernsortiment** definieren — und
darauf eine **Quote**: Zubehör darf höchstens einen bestimmten Anteil der aktiven
Deals einer Kategorie stellen. Zubehör verschwindet also nicht, es hört nur auf,
die Seite zu beherrschen.

Warum eine Quote und kein Verbot: sie korrigiert sich selbst. Kommt an einem Tag
kein guter Laptop-Deal, bleibt der Platz knapper besetzt, statt mit dem nächsten
Kabel gefüllt zu werden. Und sie braucht keine vollständige Liste — was nicht
eingeordnet ist, gilt als unbekannt und wird wie Kernsortiment behandelt, damit
eine Lücke in der Pflege nie gute Produkte aussperrt.

Wichtig zum Zeitpunkt
---------------------
`sub_category` kommt ausschliesslich aus Keepas `/product`, NICHT aus `/deal`.
Bei der Deal-Entdeckung ist sie deshalb noch unbekannt. Die Quote greift folglich
erst nach der Anreicherung, also im stündlichen Preis-Check — nicht bei der
Aufnahme. Das ist kein Nachteil: dort steht ohnehin schon die Invariante „kein
aktiver Deal ohne Chart".

Herkunft der Namen
------------------
Alle Unterkategorien unten stammen aus der Messung vom 11.08.2026
(`/debug/subcategories`), sind also echte Keepa-Namen und nicht geraten. Der
Median-Preis war dabei der beste Hinweis auf die Rolle: „Computer-Zubehör"
liegt bei 35 €, „Laptops" bei 550 €.

Die Messung bestätigte Davids Eindruck auch in Zahlen — im Katalog stehen unter
„Computer & Zubehör" 694 Produkte in „Computer-Zubehör", aber nur 10 Laptops und
13 Desktop-PCs; unter „Küche, Haushalt & Wohnen" 679 in „Wohnaccessoires & Deko"
gegen 107 in „Elektrische Küchengeräte".
"""
from __future__ import annotations

import os

KERN     = "kern"
ZUBEHOER = "zubehoer"
UNBEKANNT = "unbekannt"

# Oberkategorie → {Unterkategorie (klein geschrieben): Rolle}.
# Was hier fehlt, gilt als UNBEKANNT und wird wie Kernsortiment behandelt.
SUBCATEGORY_ROLE: dict[str, dict[str, str]] = {
    "Computer & Zubehör": {
        "laptops":                            KERN,
        "desktop-pcs":                        KERN,
        "tablet pcs":                         KERN,
        "monitore":                           KERN,
        "netzwerk":                           KERN,
        "komponenten & ersatzteile":          KERN,
        "datenspeicher":                      KERN,
        "drucker & zubehör":                  KERN,
        "computer-zubehör":                   ZUBEHOER,
        "mäuse, tastaturen & eingabegeräte":  ZUBEHOER,
    },
    "Küche, Haushalt & Wohnen": {
        "elektrische küchengeräte":           KERN,
        "haushaltsreiniger & staubsauger":    KERN,
        "haushaltsgroßgeräte":                KERN,
        "küche, kochen & backen":             KERN,
        "waschen & bügeln":                   KERN,
        "heizen & kühlen":                    KERN,
        "möbel":                              KERN,
        "wohnaccessoires & deko":             ZUBEHOER,
        "aufbewahrung & organisation":        ZUBEHOER,
        "basteln, malen & handarbeiten":      ZUBEHOER,
        "bilder, poster, kunstdrucke & skulpturen": ZUBEHOER,
        "lichterketten":                      ZUBEHOER,
        "leuchtmittel":                       ZUBEHOER,
        "bad-beleuchtung":                    ZUBEHOER,
        "abfall & recycling":                 ZUBEHOER,
    },
    "Elektronik & Foto": {
        "fernseher & heimkino":               KERN,
        "kamera & foto":                      KERN,
        "hifi & audio":                       KERN,
        "kopfhörer & zubehör":                KERN,
        "tragbare technologie":               KERN,
        "tragbare geräte":                    KERN,
        # Median 32 € — in dieser Ebene liegen überwiegend Hüllen und Ladekabel,
        # nicht Telefone.
        "handys & zubehör":                   ZUBEHOER,
        "batterien, akkus & zubehör":         ZUBEHOER,
        "netzkabel, verteiler & adapter":     ZUBEHOER,
    },
    "Baumarkt": {
        "elektro- & handwerkzeuge":                     KERN,
        "rasenmäher & elektrische gartenwerkzeuge":     KERN,
        "garten- & bewässerungsgeräte":                 KERN,
        "grills & zubehör":                             KERN,
        "sicherheitstechnik":                           KERN,
        "küchen- & badarmaturen":                       KERN,
        "gartenmöbel & zubehör":                        KERN,
        "baubedarf":                                    ZUBEHOER,
        "eisenwaren":                                   ZUBEHOER,
        "malerbedarf, werkzeuge & tapeten":             ZUBEHOER,
        "gartendeko":                                   ZUBEHOER,
        "blumen & pflanzen":                            ZUBEHOER,
        "lagerung & heimorganisation":                  ZUBEHOER,
    },
}

# Höchstanteil Zubehör an den aktiven Deals je Oberkategorie.
# 0.40 heisst: höchstens vier von zehn Kacheln dürfen Kleinteile sein.
# Bewusst kein Verbot — Zubehör soll vorkommen, nur nicht dominieren. Fehlt ein
# Eintrag, gilt für diese Kategorie keine Grenze.
MAX_ZUBEHOER_ANTEIL: dict[str, float] = {
    "Computer & Zubehör":        0.40,
    "Küche, Haushalt & Wohnen":  0.40,
    "Elektronik & Foto":         0.40,
    "Baumarkt":                  0.50,
}

# Notausschalter ohne Deploy: falls die Quote im Betrieb zu viel wegschneidet.
QUOTA_AKTIV = os.getenv("SORTIMENT_QUOTA_AKTIV", "1") not in ("0", "false", "False")


def rolle(category: str, sub_category: str) -> str:
    """
    Rolle einer Unterkategorie. Unbekanntes gilt NICHT als Zubehör — eine
    unvollständige Liste darf gute Produkte nicht aussperren, sie darf nur
    weniger gut aufräumen.
    """
    tabelle = SUBCATEGORY_ROLE.get(category or "")
    if not tabelle:
        return UNBEKANNT
    return tabelle.get((sub_category or "").strip().lower(), UNBEKANNT)


def zuviel_zubehoer(category: str, n_zubehoer: int, n_gesamt: int) -> int:
    """
    Wie viele Zubehör-Deals sind über der Quote? 0 = alles im Rahmen.

    Gerechnet wird gegen die Gesamtzahl der aktiven Deals der Kategorie, nicht
    gegen eine feste Stückzahl — sonst wäre die Regel bei wenigen Deals sinnlos
    und bei vielen zu streng.
    """
    if not QUOTA_AKTIV or n_gesamt <= 0:
        return 0
    grenze = MAX_ZUBEHOER_ANTEIL.get(category or "")
    if grenze is None:
        return 0
    erlaubt = int(n_gesamt * grenze)
    return max(0, n_zubehoer - erlaubt)


def ist_konfiguriert() -> bool:
    """True, sobald mindestens eine Kategorie eingeordnet UND begrenzt ist."""
    return bool(SUBCATEGORY_ROLE and MAX_ZUBEHOER_ANTEIL)


# ---------------------------------------------------------------------------
# Dieselbe Tabelle, zweite Verwendung: Discovery (David, 13.08.2026)
# ---------------------------------------------------------------------------
# Die Quote oben ist ein Löschmechanismus — sie kann Zubehör verdrängen, aber
# kein einziges gutes Produkt herbeischaffen. Das Ergebnis war entsprechend:
# weniger Kacheln, gleicher Charakter. Der Fehler lag eine Stufe früher, in der
# Discovery: alle Keepa-Abfragen liefen über ROOT-Knoten und wurden nach Rabatt-
# PROZENT sortiert. In diesem Fenster stehen Kleinteile ganz oben, weil sie hohe
# Margen und damit hohe Prozentnachlässe haben. Der Filter durfte danach nur
# noch entscheiden, WELCHER Teil des Ramschs durchkommt.
#
# Keepas `includeCategories` akzeptiert aber auch Unterknoten. Fragt man direkt
# „Monitore" statt „Computer & Zubehör" ab, besteht das Fenster von vornherein
# aus Kernprodukten — und die Prozent-Sortierung darin ist sogar nützlich.
#
# Die Namen dafür stehen schon oben. Diese Funktion macht sie nur nachschlagbar.

def kern_namen(category: str) -> set[str]:
    """
    Klein geschriebene Namen der Kern-Unterkategorien einer Oberkategorie.

    Bewusst NUR die explizit als KERN markierten: UNBEKANNT gilt bei der Quote
    als Kern (eine Pflegelücke darf nichts aussperren), bei der Discovery wäre
    dieselbe Grosszügigkeit sinnlos — sie würde einfach wieder alles abfragen.
    """
    tabelle = SUBCATEGORY_ROLE.get(category or "") or {}
    return {name for name, r in tabelle.items() if r == KERN}


def hat_kern_namen() -> bool:
    """True, wenn für mindestens eine Oberkategorie Kernknoten definiert sind."""
    return any(kern_namen(c) for c in SUBCATEGORY_ROLE)
