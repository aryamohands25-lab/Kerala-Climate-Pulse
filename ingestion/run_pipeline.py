"""run_pipeline.py – Orchestrates bronze -> silver -> gold in one command.

    python -m ingestion.run_pipeline                 # full run
    python -m ingestion.run_pipeline --skip-ingest   # reuse today's bronze files
    python -m ingestion.run_pipeline --with-anomaly --export
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from ingestion.anomaly import run_anomaly_detection
from ingestion.db import get_engine, init_schema
from ingestion.export_gold import export_gold
from ingestion.ingest import ingest_all
from ingestion.load import (
    date_span,
    load_dim_date,
    load_dim_district,
    load_silver,
    refresh_fact,
)
from ingestion.logger import get_logger
from ingestion.quality_checks import quarantine_out_of_range, run_checks, write_report
from ingestion.timeutil import now_local
from ingestion.transform import build_silver_frame

log = get_logger(__name__)


def _log_run(engine: Engine, run_id: str, started: pd.Timestamp, status: str,
             rows: int | None = None, quality: str | None = None, message: str = "") -> None:
    """Insert on first call, update afterwards (single row per run)."""
    params = dict(
        run_id=run_id, started=started.to_pydatetime(), finished=now_local().to_pydatetime(),
        status=status, rows=rows, quality=quality, message=message[:500],
    )
    with engine.begin() as conn:
        updated = conn.execute(
            text(
                "UPDATE pipeline_run_log SET finished_at=:finished, status=:status, "
                "rows_loaded=:rows, quality_status=:quality, message=:message WHERE run_id=:run_id"
            ),
            params,
        ).rowcount
        if not updated:
            conn.execute(
                text(
                    "INSERT INTO pipeline_run_log (run_id, started_at, finished_at, status, "
                    "rows_loaded, quality_status, message) VALUES "
                    "(:run_id, :started, :finished, :status, :rows, :quality, :message)"
                ),
                params,
            )


def run(
    engine: Engine | None = None,
    *,
    run_date: date | None = None,
    skip_ingest: bool = False,
    with_anomaly: bool = False,
    export: bool = False,
    districts: pd.DataFrame | None = None,
    bronze_dir: Path | None = None,
    reports_dir: Path = Path("reports"),
    now: pd.Timestamp | None = None,
    session=None,
) -> bool:
    """Run the whole pipeline. Returns True on success, False if DQ gate failed."""
    engine = engine or get_engine()
    now = now if now is not None else now_local()
    run_date = run_date or now.date()
    districts = districts if districts is not None else pd.read_csv(settings.districts_csv)
    bronze_dir = Path(bronze_dir or settings.bronze_dir)
    run_id, started = str(uuid.uuid4()), now_local()

    init_schema(engine)
    _log_run(engine, run_id, started, "RUNNING")
    try:
        # 1. Bronze
        if not skip_ingest:
            ingest_all(run_date, districts, session=session, bronze_dir=bronze_dir)

        # 2. Silver frame + quality gate (before anything is written)
        df = build_silver_frame(bronze_dir, run_date, districts, now)
        report = run_checks(df, set(districts["district_id"].astype(int)), now)
        path = write_report(report, reports_dir)
        log.info("Quality report: %s (overall %s)", path, report.overall)
        if report.has_critical:
            _log_run(engine, run_id, started, "FAILED", 0, report.overall, "Critical data quality failure")
            log.error("Critical data quality failure - nothing loaded into silver")
            return False

        df, nulled = quarantine_out_of_range(df)
        if nulled:
            log.warning("Nulled %d out-of-range values before load", nulled)

        # 3. Silver + gold
        load_dim_district(engine, districts)
        start, end = date_span(df)
        load_dim_date(engine, start, end)
        rows = load_silver(engine, df, now)
        refresh_fact(engine)

        # 4. Optional steps
        if with_anomaly:
            run_anomaly_detection(engine)
        if export:
            export_gold(engine)

        _log_run(engine, run_id, started, "SUCCESS", rows, report.overall, "ok")
        log.info("Pipeline finished: %d rows loaded", rows)
        return True
    except Exception as exc:
        _log_run(engine, run_id, started, "FAILED", None, None, f"{type(exc).__name__}: {exc}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Kerala Climate Pulse pipeline")
    parser.add_argument("--skip-ingest", action="store_true", help="reuse existing bronze files")
    parser.add_argument("--run-date", type=date.fromisoformat, help="bronze folder date (YYYY-MM-DD)")
    parser.add_argument("--with-anomaly", action="store_true", help="run Isolation Forest step")
    parser.add_argument("--export", action="store_true", help="write gold CSVs to data/gold")
    args = parser.parse_args()
    ok = run(
        run_date=args.run_date,
        skip_ingest=args.skip_ingest,
        with_anomaly=args.with_anomaly,
        export=args.export,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
