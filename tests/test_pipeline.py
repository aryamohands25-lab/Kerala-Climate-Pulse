from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from ingestion.anomaly import score_frame
from ingestion.run_pipeline import run
from tests.factories import HEAVY_RAIN_DISTRICT, NOW, POOR_AQI_DISTRICT, RUN_DATE, write_bronze


def _run(engine, bronze_dir, districts, tmp_path, **kw):
    return run(engine, run_date=RUN_DATE, skip_ingest=True, districts=districts,
               bronze_dir=bronze_dir, reports_dir=tmp_path / "reports", now=NOW, **kw)


def _count(engine, table):
    with engine.connect() as c:
        return c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def test_full_pipeline_populates_every_layer(sqlite_engine, bronze_dir, districts, tmp_path):
    assert _run(sqlite_engine, bronze_dir, districts, tmp_path) is True
    assert _count(sqlite_engine, "silver_weather_hourly") == 14 * 192
    assert _count(sqlite_engine, "fact_weather") == 14 * 192
    assert _count(sqlite_engine, "dim_district") == 14
    assert (tmp_path / "reports" / "quality_report_latest.md").exists()
    with sqlite_engine.connect() as c:
        status = c.execute(text("SELECT status FROM pipeline_run_log")).scalar()
    assert status == "SUCCESS"


def test_pipeline_is_idempotent(sqlite_engine, bronze_dir, districts, tmp_path):
    _run(sqlite_engine, bronze_dir, districts, tmp_path)
    _run(sqlite_engine, bronze_dir, districts, tmp_path)
    assert _count(sqlite_engine, "silver_weather_hourly") == 14 * 192
    assert _count(sqlite_engine, "fact_weather") == 14 * 192


def test_critical_dq_failure_loads_nothing(sqlite_engine, tmp_path, districts):
    bronze = tmp_path / "b"
    write_bronze(bronze, districts, skip_district_ids=(5,))
    assert _run(sqlite_engine, bronze, districts, tmp_path) is False
    assert _count(sqlite_engine, "silver_weather_hourly") == 0
    with sqlite_engine.connect() as c:
        assert c.execute(text("SELECT status FROM pipeline_run_log")).scalar() == "FAILED"


def test_out_of_range_values_never_reach_silver(sqlite_engine, tmp_path, districts):
    bronze = tmp_path / "b"
    def inject_bad_temperature(kind, district_id, payload):
        if kind == "weather" and district_id == 1:
            payload["hourly"]["temperature_2m"][0] = 99.0

    write_bronze(bronze, districts, mutate=inject_bad_temperature)
    assert _run(sqlite_engine, bronze, districts, tmp_path) is True
    with sqlite_engine.connect() as c:
        assert c.execute(text("SELECT MAX(temperature_c) FROM silver_weather_hourly")).scalar() < 50


def test_gold_views_produce_expected_analytics(sqlite_engine, bronze_dir, districts, tmp_path):
    _run(sqlite_engine, bronze_dir, districts, tmp_path)
    with sqlite_engine.connect() as c:
        rain = c.execute(text("SELECT district_id, observed_value, severity FROM vw_alerts "
                              "WHERE alert_type='HEAVY_RAIN'")).all()
        aqi = c.execute(text("SELECT district_id, severity FROM vw_alerts "
                             "WHERE alert_type='POOR_AIR_QUALITY'")).all()
        rolling = c.execute(text("SELECT rain_7d_mm, rain_3d_mm FROM vw_rolling_rainfall "
                                 "WHERE district_id=:i ORDER BY full_date DESC LIMIT 1"),
                            {"i": HEAVY_RAIN_DISTRICT}).one()
        latest = c.execute(text("SELECT COUNT(*), MAX(observed_at) FROM vw_latest_reading")).one()
    assert [r[0] for r in rain] == [HEAVY_RAIN_DISTRICT] and rain[0][2] == "HEAVY"
    assert [r[0] for r in aqi] == [POOR_AQI_DISTRICT]
    assert rolling[0] >= rolling[1] >= 80  # 7-day window contains the 80 mm day
    assert latest[0] == 14 and str(latest[1]).startswith("2026-10-24 14:00")


def test_anomaly_scoring_flags_injected_outlier():
    rng = pd.Series(range(120))
    df = pd.DataFrame({
        "district_id": 1,
        "observed_at": pd.date_range("2026-10-17", periods=120, freq="h"),
        "temperature_c": 26 + (rng % 5) * 0.2,
        "humidity_pct": 80.0, "rainfall_mm": 0.0, "wind_speed_kmh": 10.0, "pm2_5": 20.0,
    })
    df.loc[60, ["temperature_c", "rainfall_mm", "wind_speed_kmh", "pm2_5"]] = [41, 90, 120, 300]
    out = score_frame(df)
    assert bool(out.loc[out.observed_at == df.loc[60, "observed_at"], "is_anomaly"].iloc[0])
    assert out.is_anomaly.sum() <= 5


def test_anomaly_skips_districts_with_too_little_data():
    df = pd.DataFrame({"district_id": 1, "observed_at": pd.date_range("2026-10-17", periods=10, freq="h"),
                       "temperature_c": 1.0, "humidity_pct": 1.0, "rainfall_mm": 0.0,
                       "wind_speed_kmh": 1.0, "pm2_5": 1.0})
    assert score_frame(df).empty
