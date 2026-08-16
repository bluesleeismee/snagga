"""
Regressionstests für die Allzeittief-Logik (resolve_atl / determine_tag).

Kern-Invariante, die dreimal gebrochen wurde:
  "Allzeittiefpreis" darf NUR erscheinen, wenn der aktuelle Preis das TIEFSTE
  je BELEGTE Preisniveau erreicht oder unterbietet — und dieses Tief muss aus
  echten Daten stammen (Keepa stats.atl aus /product oder Minimum einer echten
  Preishistorie), nicht aus dem avg365-Proxy des /deal-Endpoints und niemals
  aus dem aktuellen Preis selbst.

Ausführen:  python -m pytest test_atl_tags.py -q     (oder: python test_atl_tags.py)
"""
from datetime import datetime, timedelta

from scoring import (
    ATL_TOL,
    resolve_atl,
    atl_for_display,
    determine_tag,
    best_price_since_months,
)


def _hist(prices, days_apart=30):
    """[(preis, ts), …] chronologisch, ältester zuerst."""
    now = datetime.utcnow()
    n = len(prices)
    return [(p, now - timedelta(days=days_apart * (n - 1 - i))) for i, p in enumerate(prices)]


# ---------------------------------------------------------------------------
# Der konkrete Produktionsfehler (Etseinri HDMI, B0…, 26.07.2026)
# ---------------------------------------------------------------------------

def test_hdmi_kabel_kein_allzeittief():
    """
    Realfall: aktueller Preis 30,56 €, echtes Tief 22,59 €, Ø Gesamt 30,43 €.
    Der /deal-Endpoint hatte 30,43 € als ATL-Proxy in all_time_low geschrieben,
    der stündliche Preis-Check reichte ihn als bestätigt weiter → Badge
    "ALLZEITTIEFPREIS" neben einem Chart, der 22,59 € zeigt.
    """
    current = 30.56
    history = [p for p, _ in _hist([34.34, 51.0, 28.9, 22.59, 24.5, 30.43, 30.56])]

    # 1) Proxy allein ist KEIN Beleg — auch wenn er in der DB steht.
    atl, ok = resolve_atl(current, stored_atl=30.43, stored_confirmed=False)
    assert (atl, ok) == (0.0, False)

    # 2) Mit echter Historie kommt das WAHRE Tief heraus, nicht der Proxy.
    atl, ok = resolve_atl(current, stored_atl=30.43, stored_confirmed=False,
                          history_prices=history)
    assert ok is True
    assert atl == 22.59

    # 3) Und der Tag ist damit garantiert nicht "Allzeittiefpreis".
    tag = determine_tag(current, atl, avg90=30.0, avg180=32.0,
                        atl_confirmed=ok, months_since_lower=None)
    assert tag != "Allzeittiefpreis"


def test_aktueller_preis_ist_niemals_tief_beleg():
    """
    Die Wurzel aller drei Fehlversuche: der aktuelle Preis stand in der
    min()-Kandidatenliste bzw. war `or current_price`-Fallback. Damit lag das
    "Tief" nie über dem aktuellen Preis und `current <= atl` konnte nicht mehr
    fehlschlagen — jedes Produkt ohne Keepa-Tief wurde zum Allzeittiefpreis.
    """
    atl, ok = resolve_atl(99.99)                      # gar keine Belege
    assert (atl, ok) == (0.0, False)
    assert determine_tag(99.99, atl, 120.0, 130.0, atl_confirmed=ok) != "Allzeittiefpreis"

    # Auch eine Ein-Punkt-"Historie" (= der gerade eingefügte aktuelle Preis)
    # darf sich nicht selbst zum Tief erklären.
    atl, ok = resolve_atl(99.99, history_prices=[99.99])
    assert (atl, ok) == (0.0, False)


def test_echtes_allzeittief_wird_vergeben():
    """Gegenprobe: erreicht der Preis das belegte Tief, MUSS der Tag kommen."""
    history = [p for p, _ in _hist([60.0, 55.0, 48.0, 42.0])]
    atl, ok = resolve_atl(42.0, keepa_atl=42.0, history_prices=history)
    assert (atl, ok) == (42.0, True)
    assert determine_tag(42.0, atl, 52.0, 55.0, atl_confirmed=ok) == "Allzeittiefpreis"


def test_neues_tief_unterbietet_stale_keepa_stat():
    """Keepas Stats laufen einem frischen Tief nach → current < atl ist gültig."""
    atl, ok = resolve_atl(39.0, keepa_atl=42.0, history_prices=[60.0, 55.0, 42.0])
    assert ok is True and atl == 42.0
    assert determine_tag(39.0, atl, 52.0, 55.0, atl_confirmed=ok) == "Allzeittiefpreis"
    # Anzeige klemmt auf den aktuellen Preis (ein Tief über dem Preis ist unmöglich)…
    assert atl_for_display(atl, 39.0) == 39.0
    # …aber das Klemmen darf den Claim nicht selbst erzeugen (siehe Test unten).


def test_klemmen_erzeugt_keinen_claim():
    """
    atl_for_display() klemmt auf den aktuellen Preis. Würde dieser geklemmte
    Wert in die Tag-Entscheidung fliessen, wäre `current <= atl` immer wahr.
    Deshalb: Anzeige-Wert und Entscheidungs-Wert sind getrennt.
    """
    current, atl = 30.56, 22.59
    assert atl_for_display(atl, current) == 22.59      # Tief < Preis → unverändert
    assert determine_tag(current, atl, 30.0, 32.0, atl_confirmed=True) != "Allzeittiefpreis"


def test_toleranz_ist_null():
    """3 % Toleranz beworb einen Preis 3 % ÜBER dem Tief als Allzeittief."""
    assert ATL_TOL == 1.0
    # 1 Cent über dem Tief ist kein Allzeittief mehr.
    assert determine_tag(22.60, 22.59, 30.0, 32.0, atl_confirmed=True) != "Allzeittiefpreis"
    assert determine_tag(22.59, 22.59, 30.0, 32.0, atl_confirmed=True) == "Allzeittiefpreis"
    # Der alte Bug-Wert läge klar innerhalb der früheren 3-%-Toleranz:
    assert 22.60 <= 22.59 * 1.03


def test_historisch_guenstig_braucht_belegtes_tief():
    """
    Der Zweig "nahe am Tief" lief früher auf den avg365-Proxy: ein Preis nahe
    dem JAHRESDURCHSCHNITT wurde als "Historisch günstig" verkauft.
    """
    # Preis ≈ Ø365-Proxy (30,43 €), kein belegtes Tief, kein echter Rabatt.
    tag = determine_tag(30.56, 0.0, avg90=31.0, avg180=32.0, atl_confirmed=False)
    assert tag != "Historisch günstig"


def test_unbelegtes_tief_liefert_weiterhin_ein_urteil():
    """Ohne belegtes Tief soll die Kachel nicht urteilslos bleiben (Ø-Zweige)."""
    assert determine_tag(50.0, 0.0, avg90=100.0, avg180=100.0, atl_confirmed=False) != ""
    assert determine_tag(80.0, 0.0, avg90=100.0, avg180=100.0, atl_confirmed=False) != ""


# ---------------------------------------------------------------------------
# "Bester Preis seit N Monaten" — muss zum Chart daneben passen
# ---------------------------------------------------------------------------

def test_bester_preis_seit_respektiert_gleich_guenstigen_punkt():
    """Ein gleich günstiger Punkt vor 1 Monat bricht "seit über 1 Jahr"."""
    now = datetime.utcnow()
    history = [
        (40.0, now - timedelta(days=400)),
        (29.91, now - timedelta(days=380)),
        (40.0, now - timedelta(days=200)),
        (29.91, now - timedelta(days=30)),   # derselbe Preis, erst vor 1 Monat
        (40.0, now - timedelta(days=10)),
        (29.91, now - timedelta(days=1)),
    ]
    months = best_price_since_months(history, 29.91)
    assert months is None or months < 12


def test_bester_preis_seit_ignoriert_juengeres_tief_nicht():
    """
    Realfall Bomann-Kühlschrank B06XC43BF6 (11.08.2026): aktuell 199,90 €, wenige
    Tage zuvor 184,99 € und 187,00 €. Die Seite behauptete "Bester Preis seit 8
    Monaten" — direkt neben dem Chart, in dem das tiefere Niveau zu sehen war.

    Ursache: die Schleife übersprang die jüngste Strecke, bis der Preis einmal
    spürbar ÜBER dem aktuellen lag. Damit verschwanden auch die echten Tiefs in
    dieser Strecke. Ein spürbar tieferer Punkt dort heisst: kein bester Preis.
    """
    now = datetime.utcnow()
    history = [
        (229.0, now - timedelta(days=200)),
        (217.0, now - timedelta(days=120)),
        (229.0, now - timedelta(days=60)),
        (217.0, now - timedelta(days=20)),
        (187.0, now - timedelta(days=8)),    # günstiger als jetzt …
        (184.99, now - timedelta(days=6)),   # … und noch günstiger
        (199.9, now - timedelta(days=2)),
        (199.9, now - timedelta(days=1)),
    ]
    assert best_price_since_months(history, 199.9) is None


def test_bester_preis_seit_toleriert_rundungsrauschen():
    """
    Gegenprobe zum Test darüber: 0,2 % unter dem aktuellen Preis ist Keepa-
    Rundungsrauschen und darf die Aussage NICHT kippen — sonst hätte praktisch
    kein Produkt mehr ein Urteil.
    """
    now = datetime.utcnow()
    history = [
        (300.0, now - timedelta(days=400)),
        (295.0, now - timedelta(days=300)),
        (300.0, now - timedelta(days=100)),
        (209.6, now - timedelta(days=5)),    # 0,19 % unter 210 → Rauschen
        (210.0, now - timedelta(days=1)),
    ]
    months = best_price_since_months(history, 210.0)
    assert months is not None and months >= 3


def test_bester_preis_seit_ohne_teureren_punkt_ist_none():
    """Flache Linie / aktuell teuerster Stand → keine belastbare Aussage."""
    assert best_price_since_months([p for p in _hist([20.0, 20.0, 20.0])], 20.0) is None


def test_tag_prioritaet_atl_vor_monaten():
    history = [p for p, _ in _hist([60.0, 50.0, 40.0])]
    atl, ok = resolve_atl(40.0, keepa_atl=40.0, history_prices=history)
    assert determine_tag(40.0, atl, 55.0, 58.0, atl_confirmed=ok,
                         months_since_lower=18) == "Allzeittiefpreis"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL {name}: {e or 'assert'}")
    print("\nAlle Tests bestanden." if not failed else f"\n{failed} Test(s) fehlgeschlagen.")
    raise SystemExit(1 if failed else 0)


# ── Zeitspanne der Historie (16.08.2026) ───────────────────────────────────

def test_kurze_historie_belegt_kein_allzeittief():
    """
    Drei Punkte über drei Wochen sind kein Beleg für „Allzeittief".

    Gemessen am 16.08.2026: acht von sechzehn frisch entdeckten Deals trugen den
    Badge, durchweg frisch gelistete No-Name-Ware, deren Preis seit der
    Einführung nur gefallen war. Formal korrekt, für den Kunden irreführend.
    """
    from datetime import datetime, timedelta
    from scoring import resolve_atl, historien_spanne_tage, ATL_MIN_HISTORY_DAYS

    heute = datetime(2026, 8, 16)
    kurz = [(54.46, heute - timedelta(days=20)),
            (44.90, heute - timedelta(days=10)),
            (37.83, heute)]
    lang = [(54.46, heute - timedelta(days=300)),
            (44.90, heute - timedelta(days=150)),
            (37.83, heute)]

    assert historien_spanne_tage(kurz) < ATL_MIN_HISTORY_DAYS
    assert historien_spanne_tage(lang) >= ATL_MIN_HISTORY_DAYS

    atl, ok = resolve_atl(37.83, history_prices=[p for p, _ in kurz],
                          history_span_days=historien_spanne_tage(kurz))
    assert ok is False, "Kurze Historie darf kein bestätigtes Tief ergeben"
    assert atl > 0, "Der Wert bleibt als Anker erhalten, nur unbestätigt"

    atl, ok = resolve_atl(37.83, history_prices=[p for p, _ in lang],
                          history_span_days=historien_spanne_tage(lang))
    assert ok is True and atl == 37.83


def test_kurze_historie_entwertet_auch_keepa_atl_und_gespeichertes_flag():
    """
    Die Spanne schlägt jede Quelle: `enrich_with_keepa` mischt selbst schon das
    History-Minimum in `all_time_low`, und ein früher gesetztes `atl_confirmed`
    darf eine heute unbelegbare Aussage nicht am Leben halten.
    """
    from scoring import resolve_atl
    _, ok = resolve_atl(37.83, keepa_atl=37.83, stored_atl=37.83,
                        stored_confirmed=True, history_prices=[54.0, 44.0, 37.83],
                        history_span_days=20.0)
    assert ok is False


def test_spanne_vertraegt_text_zeitstempel_aus_der_db():
    """price_history.timestamp ist eine TEXT-Spalte — der Helfer muss das können."""
    from scoring import historien_spanne_tage
    punkte = [(54.46, "2026-01-01 00:00:00"), (37.83, "2026-08-16 00:00:00")]
    assert historien_spanne_tage(punkte) > 200
    assert historien_spanne_tage([(1.0, "kaputt"), (2.0, None)]) == 0.0
