"""Runs the pipeline on a real PostgreSQL server. Opt-in: RUN_PG_TESTS=1.

Uses the POSTGRES_* settings (see .env). Point them at a scratch database -
the test creates/updates tables in it.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from ingestion.db import get_engine
from ingestion.run_pipeline import run
from tests.factories import HEAVY_RAIN_DISTRICT, NOW, RUN_DATE

pytestmark = pytest.mark.skipif(os.getenv("RUN_PG_TESTS") != "1", reason="set RUN_PG_TESTS=1")


def test_pipeline_on_postgres_is_idempotent_and_views_work(bronze_dir, districts, tmp_path):
    engine = get_engine()
    assert engine.dialect.name == "postgresql"
    for _ in range(2):
        assert run(engine, run_date=RUN_DATE, skip_ingest=True, districts=districts,
                   bronze_dir=bronze_dir, reports_dir=tmp_path / "r", now=NOW, with_anomaly=True)
    with engine.connect() as c:
        silver = c.execute(text("SELECT COUNT(*) FROM silver_weather_hourly")).scalar()
        fact = c.execute(text("SELECT COUNT(*) FROM fact_weather")).scalar()
        alert = c.execute(text("SELECT district_id FROM vw_alerts WHERE alert_type='HEAVY_RAIN'")).scalar()
        rank1 = c.execute(text("SELECT COUNT(*) FROM vw_district_rankings WHERE rain_rank_today = 1")).scalar()
    assert silver >= 14 * 192 and fact == silver
    assert alert == HEAVY_RAIN_DISTRICT and rank1 >= 1
