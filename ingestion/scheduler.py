"""scheduler.py – Tiny in-container scheduler (alternative to cron / GitHub Actions).

    python -m ingestion.scheduler          # runs now, then every hour at :10
"""
from __future__ import annotations

import time

import schedule

from ingestion.logger import get_logger
from ingestion.run_pipeline import run

log = get_logger(__name__)


def job() -> None:
    """One pipeline run; never lets an exception kill the scheduler loop."""
    try:
        run(with_anomaly=True, export=True)
    except Exception:  # noqa: BLE001
        log.exception("Scheduled pipeline run failed; will retry next cycle")


def main() -> None:
    schedule.every().hour.at(":10").do(job)
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
