"""
Aufbewahrung für deal_observations: erst verdichten, dann Rohzeilen löschen.

Warum es das gibt
-----------------
`deal_observations` protokolliert jeden Keepa-Kandidaten inkl. der verworfenen
(eine Zeile pro ASIN und Tag). Gemessen wächst die Tabelle mit ~2.800 Zeilen/Tag
— doppelt so viel wie beim Bau geschätzt. Hochgerechnet sind das ~1 Mio. Zeilen
und 150–250 MB im Jahr, bei einem Supabase-Limit von 500 MB. Ohne Regel läuft
die Datenbank irgendwann im Frühjahr 2027 voll, und zwar an der Stelle, an der
auch die Produktdaten liegen.

Warum nicht einfach löschen
---------------------------
Die Tabelle existiert für die Datenstory und für Langzeitaussagen ("wie viele
beworbene Angebote sind über das Jahr wirklich günstig?"). Ein reines
"DELETE älter als N Tage" würde genau diese Reihe kappen. Deshalb wird jeder
abgeschlossene Tag vorher zu `deal_observation_daily` verdichtet: eine Zeile pro
Tag × Kategorie × Ablehnungsgrund statt einer pro ASIN. Das sind ~100–200
Zeilen/Tag statt 2.800 (~99 % kleiner) und beantwortet alle Fragen der
Auswertung. Verloren geht nur die ASIN-Ebene — die braucht sie nicht.

Reihenfolge ist bewusst: verdichten, prüfen, erst dann löschen. Schlägt die
Verdichtung fehl, wird nichts gelöscht.

Methodische Grenze, die in jede Veröffentlichung gehört (gilt unverändert auch
für die verdichteten Zahlen): Keepas /deal-Endpoint liefert bereits vorgefiltert
nur Angebote mit mind. −15 % gegenüber Keepas eigener Referenz. Grundgesamtheit
ist "als Rabatt beworbene Angebote", NICHT "alle Amazon-Angebote".
"""
import os
from datetime import timedelta

from database import get_pool

# Wie lange die ASIN-genauen Rohzeilen bleiben. 120 Tage decken die Datenstory
# im Oktober (Erfassung startete am 09.08.2026) mit Reserve ab und halten die
# Rohtabelle bei ~340.000 Zeilen / ~50 MB statt unbegrenzt zu wachsen.
# Über Env verstellbar, damit sich vor einer Auswertung ohne Deploy verlängern
# lässt. 0 = Rohdaten nie löschen (nur verdichten).
OBSERVATION_RETENTION_DAYS = int(os.getenv("OBSERVATION_RETENTION_DAYS", "120"))

# Verdichtet wird immer nur bis einschliesslich gestern: der laufende Tag ist
# unvollständig (der Job läuft stündlich), eine Verdichtung davon wäre falsch
# und würde durch ON CONFLICT auch nicht mehr korrigiert.
_ROLLUP_SQL = """
INSERT INTO deal_observation_daily
    (observed_day, category, reject_reason, accepted,
     n, n_disc, disc_avg, disc_median, price_median, rating_avg, reviews_median)
SELECT
    observed_day,
    COALESCE(category, ''),
    COALESCE(reject_reason, ''),
    accepted,
    COUNT(*),
    COUNT(*) FILTER (WHERE avg90 > 0),
    COALESCE(AVG(100.0 * (current_price - avg90) / NULLIF(avg90, 0)), 0),
    COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY 100.0 * (current_price - avg90) / NULLIF(avg90, 0)), 0),
    COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_price), 0),
    COALESCE(AVG(NULLIF(rating, 0)), 0),
    COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY reviews), 0)
FROM deal_observations
WHERE observed_day < CURRENT_DATE
  AND observed_day > COALESCE($1::date, DATE '2000-01-01')
GROUP BY observed_day, COALESCE(category, ''), COALESCE(reject_reason, ''), accepted
ON CONFLICT (observed_day, category, reject_reason, accepted) DO UPDATE SET
    n              = EXCLUDED.n,
    n_disc         = EXCLUDED.n_disc,
    disc_avg       = EXCLUDED.disc_avg,
    disc_median    = EXCLUDED.disc_median,
    price_median   = EXCLUDED.price_median,
    rating_avg     = EXCLUDED.rating_avg,
    reviews_median = EXCLUDED.reviews_median
"""


async def rollup_and_prune() -> dict:
    """
    Täglich: abgeschlossene Tage verdichten, danach zu alte Rohzeilen löschen.

    Fehlertolerant wie das Protokoll selbst — die Statistik darf den Betrieb
    nie gefährden. Bei einem Fehler in der Verdichtung wird NICHT gelöscht.
    """
    pool = await get_pool()
    result: dict = {"rolled_up_from": None, "deleted": 0, "raw_rows": 0, "daily_rows": 0}

    try:
        async with pool.acquire() as conn:
            # Nur neue Tage verdichten: alles bis zum letzten bereits verdichteten
            # Tag minus 1 überspringen. Der letzte verdichtete Tag selbst wird
            # erneut gerechnet — er könnte beim letzten Lauf noch unvollständig
            # gewesen sein, ON CONFLICT DO UPDATE korrigiert ihn dann.
            last_day = await conn.fetchval(
                "SELECT MAX(observed_day) FROM deal_observation_daily"
            )
            cutoff = None
            if last_day is not None:
                cutoff = last_day - timedelta(days=1)
            result["rolled_up_from"] = str(cutoff) if cutoff else "Anfang"

            await conn.execute(_ROLLUP_SQL, cutoff)

            if OBSERVATION_RETENTION_DAYS > 0:
                # Nur löschen, was nachweislich verdichtet ist: kein Rohtag darf
                # verschwinden, für den keine Tageszeile existiert.
                deleted = await conn.execute(
                    "DELETE FROM deal_observations o "
                    "WHERE o.observed_day < CURRENT_DATE - $1::int "
                    "  AND EXISTS (SELECT 1 FROM deal_observation_daily d "
                    "              WHERE d.observed_day = o.observed_day)",
                    OBSERVATION_RETENTION_DAYS,
                )
                # asyncpg liefert "DELETE <n>"
                try:
                    result["deleted"] = int(str(deleted).split()[-1])
                except (ValueError, IndexError):
                    result["deleted"] = 0

            result["raw_rows"] = await conn.fetchval(
                "SELECT COUNT(*) FROM deal_observations") or 0
            result["daily_rows"] = await conn.fetchval(
                "SELECT COUNT(*) FROM deal_observation_daily") or 0

        print(f"[retention] verdichtet ab {result['rolled_up_from']} · "
              f"{result['deleted']} Rohzeilen gelöscht · "
              f"{result['raw_rows']} roh / {result['daily_rows']} verdichtet")
    except Exception as e:
        print(f"[retention] fehlgeschlagen (unkritisch, es wurde nichts gelöscht): {e}")
        result["error"] = str(e)

    return result
