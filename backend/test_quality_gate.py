"""
Regressionstests für den Filter-Neuaufbau (David, 15.08.2026).

Jeder Test hier steht für einen Fehler, der Snagga schon einmal Geld oder
Glaubwürdigkeit gekostet hat. Sie sind wieder eingebaut, sobald jemand eine der
Zeilen für „zu streng" hält und lockert.

Vorgeschichte in einem Satz: Am 15.08.2026 standen noch 29 aktive Deals, und der
teuerste Fund des Tages war eine Einlagesohle. Ursache war nicht ein zu strenger
Filter, sondern eine Kette von Regeln, die gegen die falschen Zahlen gemessen
haben.
"""
from scoring import (
    hard_filter_reason,
    calculate_deal_score,
    QUALITY_DISCOUNT_FACTOR,
    QUALITY_MIN_ERSPARNIS_EUR,
)
import sortiment


def _fall(**kw):
    """Ein Kandidat, der alle übrigen Hard Filter besteht."""
    d = dict(
        rating=4.5, reviews=800, sales_rank=3_000,
        category="Elektronik & Foto", sub_category="Kopfhörer & Zubehör",
        current=100.0, avg90=120.0, avg30=118.0,
        title="Sony WH-1000XM5", brand="sony",
    )
    d.update(kw)
    return hard_filter_reason(**d)


# ── 1. Die Referenz ist der 90-Tage-Ø, und er ist Pflicht ──────────────────
# Vorher hiess der geprüfte Wert „avg90", war aber Keepas WOCHEN-Durchschnitt
# (DealInterval: Tag/Woche/Monat/90 Tage, gelesen als Ø30/Ø90/Ø180/Ø365). Gegen
# den Wochenschnitt sind selbst 20 % nichts — jedes Kleinteil mit normalem
# Preisgezappel erfüllt das mehrmals im Monat.

def test_ohne_90_tage_historie_abgelehnt():
    """Kein Ø90 → keine Aussage über den Kaufzeitpunkt und ein leerer Chart."""
    assert _fall(avg90=0.0) == "keine_referenz_90t"


def test_rabatt_unter_schwelle_faellt_durch():
    # 115 von 120 sind 4,2 % — unter den geforderten 10 %.
    assert _fall(current=115.0, avg30=119.0) == "rabatt_zu_klein"


def test_schwelle_ist_exakt_der_faktor():
    """Genau auf der Schwelle besteht der Deal, einen Cent darüber nicht."""
    avg90 = 120.0
    genau = round(avg90 * QUALITY_DISCOUNT_FACTOR, 2)
    assert _fall(current=genau, avg30=avg90) is None
    assert _fall(current=genau + 0.5, avg30=avg90) == "rabatt_zu_klein"


# ── 2. Mindestersparnis in Euro ────────────────────────────────────────────
# 10 % sind bei 25 € genau 2,50 €. Rechnerisch ein Deal, aber niemand stellt
# dafür den Wecker. Diese Regel ersetzt elf kategorieabhängige Preisgrenzen.

def test_prozent_erfuellt_aber_ersparnis_zu_klein():
    # 25,20 statt Ø90 28,00 = 10 % Rabatt, aber nur 2,80 € gespart.
    assert _fall(current=25.2, avg90=28.0, avg30=28.0) == "ersparnis_zu_klein"


def test_teure_ware_besteht_mit_denselben_10_prozent():
    # Dieselben 10 % auf 400 € sind 40 € — genau der Fall, den die alte
    # Preisstaffel mit drei Sonderregeln abbilden wollte.
    assert _fall(current=360.0, avg90=400.0, avg30=395.0) is None


def test_mindestersparnis_hebt_prozenthuerde_fuer_billige_ware():
    """Bei 25 € braucht es faktisch ~32 % statt 10 % — ohne Sonderregel."""
    noetig = 25.0 + QUALITY_MIN_ERSPARNIS_EUR
    assert _fall(current=25.0, avg90=noetig - 0.5, avg30=noetig) == "ersparnis_zu_klein"
    assert _fall(current=25.0, avg90=noetig, avg30=noetig) is None


# ── 3. Anti-Spike gegen den Monat ──────────────────────────────────────────

def test_alter_hochpreis_macht_noch_keinen_deal():
    """
    Ø90 hoch, weil das Produkt vor zwei Monaten teuer war — der heutige Preis
    ist aber seit Wochen der normale. Ohne diese Klammer wäre jeder Artikel
    nach einer Preissenkung monatelang ein „Deal".
    """
    assert _fall(current=100.0, avg90=200.0, avg30=90.0) == "anti_spike_30t"


def test_ohne_avg30_wird_anti_spike_uebersprungen():
    """Der stündliche Preis-Check kennt kein Ø30 — das darf nicht blockieren."""
    assert _fall(current=100.0, avg90=200.0, avg30=0.0) is None


# ── 4. RAUS: die Rolle, die vorher fehlte ──────────────────────────────────
# Bis 15.08.2026 gab es nur KERN und ZUBEHÖR, und Unbekanntes galt als KERN.
# „Wohnaccessoires & Deko" (818 Katalogprodukte, No-Name-Teppiche) wurde dadurch
# nur quotiert statt ausgeschlossen — es konkurrierte weiter um Plätze.

def test_einlagesohle_faellt_an_der_kategorie():
    """Der Auslöser des ganzen Umbaus. Sportmedizin: Median 22 €, Max 30 €."""
    assert _fall(
        category="Sport & Freizeit", sub_category="Sportmedizin",
        current=22.0, avg90=40.0, avg30=39.0,
        title="Gel Einlagesohlen Größe 42", brand="",
    ) == "kategorie_raus"


def test_deko_teppich_faellt_an_der_kategorie():
    assert _fall(
        category="Küche, Haushalt & Wohnen", sub_category="Wohnaccessoires & Deko",
        current=100.0, avg90=160.0, avg30=155.0,
        title="HUGEAR Vintage Teppich Wohnzimmer", brand="",
    ) == "kategorie_raus"


def test_fehlende_unterkategorie_blockiert_nicht():
    """
    Keepas /deal liefert die Unterkategorie NICHT — frisch entdeckte Deals haben
    das Feld leer. Würde die RAUS-Prüfung dann greifen, käme nie ein neuer Deal
    ins Regal; die Prüfung holt der stündliche Preis-Check nach.
    """
    assert _fall(sub_category="") is None


def test_smartphone_ist_kern_nicht_zubehoer():
    """
    „Handys & Zubehör" hat Median 33 €, aber an der Spitze Galaxy S25 Ultra und
    iPhone Air. Der Median misst die Masse, nicht den Wert — die Kleinteile
    darunter filtert der Mindestpreis, nicht die Kategorie.
    """
    assert sortiment.rolle("Elektronik & Foto", "Handys & Zubehör") == sortiment.KERN
    assert _fall(
        sub_category="Handys & Zubehör", current=600.0, avg90=700.0, avg30=690.0,
        title="Samsung Galaxy S25", brand="samsung",
    ) is None


# ── 5. Vertrauenssignal: Rang statt Bewertungsmasse ────────────────────────
# 500+ Bewertungen sind für No-Name-Marketplace-Ware der Normalfall und zudem
# käuflich, für Neuware dagegen unerreichbar — die alte Regel selektierte genau
# falsch herum.

def test_bewertungsmasse_allein_reicht_nicht():
    # Das Profil der Marketplace-Ware, die das Schaufenster geflutet hat:
    # 2.000 Bewertungen, 4,4 Sterne, echter Rabatt — aber schwacher Rang.
    assert _fall(
        sub_category="", brand="", title="Generic Bluetooth Kopfhörer",
        current=30.0, avg90=40.0, avg30=39.0,
        reviews=2000, rating=4.4, sales_rank=17_000,
    ) == "kein_vertrauenssignal"


def test_rangbonus_gilt_erst_ab_100_euro():
    """
    Derselbe schwache Rang ist bei einem 100-€-Gerät in Ordnung: der Rang misst
    Stückzahlen gegen den Kleinteil-Massenmarkt derselben Oberkategorie, wo sich
    Kabel um Grössenordnungen häufiger verkaufen als Kopfhörer.
    """
    assert _fall(
        sub_category="", brand="", title="Generic Bluetooth Kopfhörer",
        current=100.0, avg90=120.0, avg30=118.0,
        reviews=2000, rating=4.4, sales_rank=17_000,
    ) is None


def test_neuware_mit_gutem_rang_kommt_durch():
    """Der Z-Edge-Monitor: unbekannte Marke, erst 150 Bewertungen."""
    assert _fall(
        category="Computer & Zubehör", sub_category="Monitore",
        current=189.0, avg90=220.0, avg30=218.0,
        reviews=150, rating=4.3, sales_rank=8_000,
        title="Z-Edge 240Hz Gaming Monitor", brand="Z-Edge",
    ) is None


def test_bekannte_marke_braucht_keinen_rangbeleg():
    assert _fall(
        category="Computer & Zubehör", sub_category="Monitore",
        current=189.0, avg90=220.0, avg30=218.0,
        reviews=120, rating=4.3, sales_rank=40_000,
        title="Samsung Monitor", brand="Samsung",
    ) is None


# ── 6. Kern-Knoten = das Suchfenster der Discovery ─────────────────────────

def test_kern_namen_nur_explizit_markierte():
    kern = sortiment.kern_namen("Computer & Zubehör")
    assert "monitore" in kern and "laptops" in kern
    # Zubehör und Unbekanntes gehören NICHT ins Suchfenster — sonst fragt die
    # Kern-Discovery wieder alles ab und der Umbau war umsonst.
    assert "computer-zubehör" not in kern
    assert "gibt-es-nicht" not in kern


def test_jede_oberkategorie_hat_kern_knoten():
    """
    Eine Oberkategorie ohne KERN-Eintrag wird von der Discovery nie abgefragt —
    sie kann sich nur noch zufällig über die Breitensuche füllen. Das ist fast
    immer ein Pflegefehler, kein Vorsatz.
    """
    ohne = [c for c in sortiment.oberkategorien() if not sortiment.kern_namen(c)]
    assert ohne == [], f"Oberkategorien ohne Kern-Knoten: {ohne}"


def test_gestrichene_kategorien_sind_weg():
    for weg in ("Kosmetik", "Auto & Motorrad", "Software", "Beleuchtung", "Kamera & Foto"):
        assert weg not in sortiment.KATEGORIEN
        assert sortiment.rolle(weg, "Irgendwas") == sortiment.UNBEKANNT


# ── 8. Die vier Kategorielisten dürfen nicht auseinanderlaufen ─────────────
# Genau das war die Ursache des ganzen Umbaus: Kategorie-Wissen lag verteilt in
# ROOTCAT_MAP, EXCLUDE_ROOTCATS, KEYWORD_MAP, CATEGORY_MAX_RANK und
# INCLUDE_CAT_IDS — und lief auseinander, ohne dass es jemand merkte.
#
# Am 15.08.2026, NACH dem ersten Deploy des Umbaus, war der Stand: „Spielzeug"
# und „Gewerbe/Industrie" waren als Oberkategorien beschlossen, standen aber
# gleichzeitig in EXCLUDE_ROOTCATS und fehlten in ROOTCAT_MAP — sie konnten
# nichts liefern. „Auto & Motorrad" und „Kamera & Foto" waren gestrichen, wurden
# von ROOTCAT_MAP aber weiter vergeben und kamen ungehindert herein.

def test_rootcat_map_kennt_nur_gueltige_kategorien():
    import scraper
    unbekannt = {c for c in scraper.ROOTCAT_MAP.values() if c not in sortiment.KATEGORIEN}
    assert not unbekannt, f"ROOTCAT_MAP vergibt gestrichene Kategorien: {sorted(unbekannt)}"


def test_keyword_map_kennt_nur_gueltige_kategorien():
    import scraper
    unbekannt = {c for c in scraper.KEYWORD_MAP if c not in sortiment.KATEGORIEN}
    assert not unbekannt, f"KEYWORD_MAP kennt gestrichene Kategorien: {sorted(unbekannt)}"


def test_jede_kategorie_hat_eine_rangschwelle():
    from scoring import CATEGORY_MAX_RANK
    fehlt = [c for c in sortiment.oberkategorien() if c not in CATEGORY_MAX_RANK]
    assert not fehlt, f"Ohne Rangschwelle (still 30.000): {fehlt}"


def test_jede_kategorie_ist_ueber_rootcat_erreichbar():
    """Eine Oberkategorie ohne rootCat-Eintrag kann sich nie füllen."""
    import scraper
    erreichbar = set(scraper.ROOTCAT_MAP.values())
    fehlt = [c for c in sortiment.oberkategorien() if c not in erreichbar]
    assert not fehlt, f"Nicht über ROOTCAT_MAP erreichbar: {fehlt}"


def test_keine_gewuenschte_kategorie_ist_geblockt():
    """
    Der teuerste Fehler dieser Art: Spielzeug und Gewerbe/Industrie standen in
    EXCLUDE_ROOTCATS, während sie gleichzeitig als Oberkategorie geführt wurden.
    """
    import scraper
    geblockt = [rid for rid, cat in scraper.ROOTCAT_MAP.items()
                if cat in sortiment.KATEGORIEN and rid in scraper.EXCLUDE_ROOTCATS]
    assert not geblockt, f"rootCat-IDs gewünschter Kategorien in EXCLUDE_ROOTCATS: {geblockt}"


def test_quote_ist_nach_einem_durchlauf_stabil():
    """
    Ein Durchlauf muss die Quote exakt herstellen — der nächste darf nichts mehr
    finden. Die alte Formel rechnete gegen die Gesamtzahl und brauchte mehrere
    Runden; weil zwischen zwei Läufen Backups nachrücken, kam die Kategorie nie
    zur Ruhe und deaktivierte stündlich weiter.
    """
    zub, gesamt = 5, 10
    weg = sortiment.zuviel_zubehoer("Baumarkt", zub, gesamt)
    zub, gesamt = zub - weg, gesamt - weg
    assert sortiment.zuviel_zubehoer("Baumarkt", zub, gesamt) == 0, \
        "zweiter Durchlauf räumt weiter — Rückkopplung wieder da"


def test_quote_haelt_den_versprochenen_anteil():
    """0.40 heisst: höchstens vier von zehn Kacheln sind Zubehör."""
    zub, gesamt = 8, 20        # 12 Kern
    weg = sortiment.zuviel_zubehoer("Baumarkt", zub, gesamt)
    rest_zub, rest_gesamt = zub - weg, gesamt - weg
    assert rest_zub / rest_gesamt <= 0.40 + 1e-9


def test_classify_category_laesst_nur_bekannte_durch():
    import scraper
    # Auto & Motorrad: gestrichen, rootCat wird trotzdem geliefert
    assert scraper.classify_category("Bosch Autobatterie 70Ah", root_cat=78191031) is None
    # Spielzeug: gewünscht, muss durchkommen
    assert scraper.classify_category("LEGO Technic Bagger", root_cat=12950651) == "Spielzeug"


# ── 7. Score ohne belegtes Tief ────────────────────────────────────────────

def test_score_ohne_tief_bleibt_ueber_min_score():
    """
    Der /deal-Endpoint liefert kein Allzeittief. Flösse dessen 30 % Gewicht als
    harte Null ein, scheiterte jeder frisch entdeckte Deal an MIN_SCORE (30) —
    ein „Qualitätsfilter", der in Wahrheit nur misst, ob /product schon lief.
    """
    ohne, _ = calculate_deal_score(100.0, 120.0, 0.0, 3_000,
                                   "Elektronik & Foto", 4.5, 800, title="Sony WH-1000XM5")
    mit, _ = calculate_deal_score(100.0, 120.0, 98.0, 3_000,
                                  "Elektronik & Foto", 4.5, 800, title="Sony WH-1000XM5")
    assert ohne >= 30, f"Score ohne Tief zu niedrig: {ohne}"
    assert mit > ohne, "Ein belegtes Tief muss den Score weiterhin heben"
