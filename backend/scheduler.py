"""
APScheduler — läuft täglich um 03:00 Uhr und ruft fetch_and_update_deals() auf.
"""
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper import fetch_and_update_deals

HOUR   = int(os.getenv("SCHEDULER_HOUR",   "3"))
MINUTE = int(os.getenv("SCHEDULER_MINUTE", "0"))


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        fetch_and_update_deals,
        CronTrigger(hour=HOUR, minute=MINUTE),
        id="nightly_update",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
