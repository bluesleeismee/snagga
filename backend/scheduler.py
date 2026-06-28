"""
APScheduler — stündliche Deal-Updates + nächtlicher Deep-Sync
"""
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scraper import fetch_and_update_deals, hourly_price_check, nightly_deep_sync

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

    # Stündlicher Preis-Check der aktiven Deals (30 Min versetzt)
    scheduler.add_job(
        hourly_price_check,
        IntervalTrigger(hours=1, start_date="2024-01-01 00:35:00"),
        id="hourly_price_check",
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

    return scheduler
