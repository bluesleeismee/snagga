"""
APScheduler — stündliche Deal-Updates + nächtlicher Deep-Sync
"""
import os
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scraper import (
    fetch_and_update_deals, nightly_deep_sync, hourly_keepa_price_check,
    post_next_mastodon_deal, post_next_bluesky_deal, check_and_send_price_alerts,
    seed_bestsellers, evict_stale_charts,
)

# Brache Keepa-Tokens nutzen, um den Such-Katalog aufzubauen (Stubs, keine
# Historie). Halbiert 2026-07-06 (David: Budget war "regelmässig sehr dünn",
# 600/Std = 50% des 1200/Std-Budgets war zu aggressiv und konkurrierte mit
# Preis-Check/Deep-Sync/Ad-hoc-Klicks). Jetzt ~300/Std = ~25%, lässt den
# existierenden Jobs (~258/Std) + Ad-hoc genug Luft. Env-konfigurierbar.
CATALOG_GROW_HOURLY_TOKENS = int(os.getenv("CATALOG_GROW_HOURLY_TOKENS", "300"))


async def _hourly_catalog_grow():
    """
    Stündlich brache Tokens in Katalog-Stubs investieren (Bestseller je Kategorie).
    category_offset = fortlaufender Stundenzähler seit Epoch — rotiert die
    Startposition in ROOTCAT_MAP jede Stunde weiter, sodass über ~62 Stunden
    (~2,6 Tage) jede Kategorie mal zuerst drankommt statt immer dieselben ersten.
    """
    hour_counter = int(datetime.utcnow().timestamp() // 3600)
    await seed_bestsellers(max_tokens=CATALOG_GROW_HOURLY_TOKENS, max_per_cat=300,
                            category_offset=hour_counter)

SERVICE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://snagga.onrender.com")


async def _ping():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(f"{SERVICE_URL}/health")
    except Exception:
        pass

DEEP_SYNC_HOUR   = int(os.getenv("DEEP_SYNC_HOUR",   "3"))
DEEP_SYNC_MINUTE = int(os.getenv("DEEP_SYNC_MINUTE", "0"))
HOURLY_MINUTE    = int(os.getenv("HOURLY_MINUTE",    "5"))  # jede Stunde um :05


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Stündlicher Job: neue Deals via Keepa /deals + Preis-Check
    scheduler.add_job(
        fetch_and_update_deals,
        IntervalTrigger(hours=1, start_date="2024-01-01 00:05:00"),
        id="hourly_deal_discovery",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Stündlicher Preis-Check via Keepa /product (minimal, ~250 Tokens/Run)
    # Deaktiviert Deals deren Preis nicht mehr gut ist — max. 1h Verzögerung
    scheduler.add_job(
        hourly_keepa_price_check,
        IntervalTrigger(hours=1, start_date="2024-01-01 00:30:00"),
        id="hourly_keepa_price_check",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Keep-alive: alle 10 Minuten /health pingen damit Render nicht einschläft
    scheduler.add_job(
        _ping,
        IntervalTrigger(minutes=10),
        id="keepalive_ping",
        replace_existing=True,
    )

    # Preisalarme: kurz nach dem stündlichen Preis-Check (:30) prüfen, ob ein
    # Wunschpreis erreicht ist, und Benachrichtigungen verschicken.
    scheduler.add_job(
        check_and_send_price_alerts,
        IntervalTrigger(hours=1, start_date="2024-01-01 00:40:00"),
        id="price_alert_check",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Nächtlicher Deep-Sync: vollständige Keepa /product Aktualisierung
    scheduler.add_job(
        nightly_deep_sync,
        CronTrigger(hour=DEEP_SYNC_HOUR, minute=DEEP_SYNC_MINUTE),
        id="nightly_deep_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Stündlicher Katalog-Aufbau (:50): brache Tokens → neue Such-Stubs. Findet
    # ein Bestseller-Knoten keine neuen ASINs mehr, kostet er nur den Discovery-
    # Token (~1) → der Job ist selbst-limitierend, wenn der Katalog gesättigt ist.
    scheduler.add_job(
        _hourly_catalog_grow,
        IntervalTrigger(hours=1, start_date="2024-01-01 00:50:00"),
        id="hourly_catalog_grow",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Tägliche Chart-Eviction (04:00): Historie nicht-aktiver, länger nicht
    # angesehener Produkte löschen → Schicht C bleibt klein (Deals + on-demand).
    scheduler.add_job(
        evict_stale_charts,
        CronTrigger(hour=(DEEP_SYNC_HOUR + 1) % 24, minute=0),
        id="evict_stale_charts",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Mastodon: max. 1 Post zu je einer festen Uhrzeit — bewusst NICHT stündlich.
    # Die vorherige Taktung (bis zu 3/Std., identische Hashtags) fuehrte zur
    # Spam-Sperre durch mastodon.social. 3 Posts/Tag zu festen Zeiten wirkt
    # kuratiert statt automatisiert.
    for hour in (9, 14, 19):
        scheduler.add_job(
            post_next_mastodon_deal,
            CronTrigger(hour=hour, minute=15),
            id=f"mastodon_post_{hour}",
            replace_existing=True,
            misfire_grace_time=1800,
        )

    # Bluesky: gleiche zurückhaltende Taktung wie Mastodon, aber versetzte
    # Uhrzeiten — die Kanäle sollen nicht minutengleich dasselbe posten.
    for hour in (10, 15, 20):
        scheduler.add_job(
            post_next_bluesky_deal,
            CronTrigger(hour=hour, minute=45),
            id=f"bluesky_post_{hour}",
            replace_existing=True,
            misfire_grace_time=1800,
        )

    return scheduler
