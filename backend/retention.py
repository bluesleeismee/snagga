"""
Aufbewahrung für deal_observations: erst verdichten, dann Rohzeilen löschen.

Warum es das gibt
-----------------
`deal_observations` protokolliert jeden Keepa-Kandidaten inkl. der verworfenen
(eine Zeile pro ASIN und Tag). Gemessen am 11.08.2026: 105.561 Zeilen in den
ersten drei Tagen, also **~35.000/Tag** — nicht 2.800 wie beim Bau geschätzt und
auch nicht die 2.800, von denen der Wachstumsplan noch ausging. Das sind grob
10 MB/Tag, ~3,5 GB im Jahr, bei einem Supabase-Limit von 500 MB. Ohne Regel wäre
die Datenbank in ungefähr sieben Wochen voll — und zwar an der Stelle, an der
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

# Wie lange die ASIN-genauen Rohzeilen bleiben.
#
# 14 Tage, nicht mehr. Gemessen am 11.08.2026 über die ersten drei Tage:
# 105.561 Rohzeilen, also ~35.000/Tag — nicht die ursprünglich geschätzten
# 2.800. Bei grob 250–300 Byte pro Zeile inkl. Index sind das ~10 MB/Tag.
# 120 Tage Rohdaten wären über 1 GB gewesen, das Doppelte des Supabase-Limits;
# selbst 30 Tage lägen bei ~300 MB und damit gefährlich nah dran.
#
# Der kurze Zeitraum kostet nichts, weil die Verdichtung vorher läuft: alles,
# was die Datenstory braucht, steht dauerhaft in deal_observation_daily. Die
# Rohzeilen sind nur für Stichproben auf ASIN-Ebene da, und dafür reichen zwei
# Wochen. Über Env verstellbar — vor einer Auswertung, die tiefer graben soll,
# rechtzeitig hochsetzen. 0 = Rohdaten nie löschen (nur verdichten).
OBSERVATION_RETENTION_DAYS = int(os.getenv("OBSERVATION_RETENTION_DAYS", "14"))

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
