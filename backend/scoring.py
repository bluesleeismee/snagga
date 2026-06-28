"""
Deal-Scoring, Hard-Filter und Tag-Logik für snagga.de
"""
import math
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Kategorie-Konfiguration
# ---------------------------------------------------------------------------

CATEGORY_MAX_RANK: dict[str, int] = {
    "Elektronik & Foto":           8_000,
    "Computer & Zubehör":          8_000,
    "Kamera & Foto":              10_000,
    "Games":                       5_000,
    "Baumarkt":                   30_000,
    "Drogerie & Körperpflege":    30_000,
    "Küche, Haushalt & Wohnen":   20_000,
    "Elektro-Großgeräte":         10_000,
    "Sport & Freizeit":           25_000,
    "Musikinstrumente & DJ-Equipment": 15_000,
    "Auto & Motorrad":            20_000,
}


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
) -> bool:
    """Gibt True zurück wenn das Produkt alle Mindestanforderungen erfüllt."""
    if rating < 4.0:
        return False
    if reviews < 50:
        return False

    max_rank = CATEGORY_MAX_RANK.get(category, 30_000)
    if sales_rank > 0 and sales_rank > max_rank:
        return False

    # Preis deutlich unter 90-Tage-Ø oder nahe ATL
    price_ok = False
    if avg90 > 0 and current <= avg90 * 0.85:
        price_ok = True
    if atl > 0 and current <= atl * 1.05:
        price_ok = True
    if not price_ok:
        return False

    return True


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
    score = max(0, min(100, int(raw * 100)))

    breakdown = json.dumps({
        "avg90": round(f_avg, 3),
        "atl":   round(f_atl, 3),
        "pop":   round(f_pop, 3),
        "stab":  round(f_stab, 3),
        "rank":  round(rank_f, 3),
    })
    return score, breakdown


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def determine_tag(
    current: float,
    atl: float,        # Echter ATL (nur aus /product Deep-Sync, sonst 0)
    avg90:  float,
    avg180: float,
    atl_confirmed: bool = False,  # True nur wenn ATL aus /product stammt
) -> str:
    """
    Gibt den höchstpriorisierten Tag zurück (maximal einer pro Deal).

    "Allzeittiefpreis" wird NUR vergeben wenn der echte ATL bekannt ist
    (atl_confirmed=True, kommt aus /product Deep-Sync).
    Aus /deal-Daten steht nur avg365 als Proxy — das reicht NICHT für den Tag.
    """
    # avg90 || avg180 als bester verfügbarer Referenzpreis
    ref = avg90 or avg180

    # Echter ATL nur wenn durch Deep-Sync bestätigt
    if atl_confirmed and atl > 0 and current <= atl * 1.03:
        return "Allzeittiefpreis"

    # Deutlich unter 6-Monats-Durchschnitt
    if avg180 > 0 and current <= avg180 * 0.80:
        return "Historisch günstig"

    # Deutlich unter Referenzpreis
    if ref > 0 and current <= ref * 0.70:
        return "Stark gefallen"

    # Moderat unter Referenzpreis (inkl. Fallback avg180 wenn avg90 fehlt)
    if ref > 0 and current <= ref * 0.85:
        return "Preis gefallen"

    return ""
