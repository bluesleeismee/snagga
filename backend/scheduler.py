"""
APScheduler — stündliche Deal-Updates + nächtlicher Deep-Sync
"""
import os
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scraper import fetch_and_update_deals, nightly_deep_sync, hourly_keepa_price_check

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

    # Nächtlicher Deep-Sync: vollständige Keepa /product Aktualisierung
    scheduler.add_job(
        nightly_deep_sync,
        CronTrigger(hour=DEEP_SYNC_HOUR, minute=DEEP_SYNC_MINUTE),
        id="nightly_deep_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    return scheduler
