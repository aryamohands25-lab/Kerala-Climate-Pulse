"""load.py – Write silver rows, refresh dimensions, and build the fact table."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ingestion.db import upsert
from ingestion.logger import get_logger
from ingestion.timeutil import now_local

log = get_logger(__name__)

MEASURES = [
    "temperature_c", "humidity_pct", "rainfall_mm", "wind_speed_kmh",
    "pm10", "pm2_5", "aqi",
]

# Kerala's four climate seasons (IMD): used by dim_date and the dashboard.
SEASONS = {
    1: "Winter", 2: "Winter",
    3: "Summer", 4: "Summer", 5: "Summer",
    6: "Southwest Monsoon", 7: "Southwest Monsoon", 8: "Southwest Monsoon", 9: "Southwest Monsoon",
    10: "Northeast Monsoon", 11: "Northeast Monsoon", 12: "Northeast Monsoon",
}


def _none_if_nan(value):
    return None if pd.isna(value) else float(value)


def silver_records(df: pd.DataFrame, loaded_at: pd.Timestamp) -> list[dict]:
    """DataFrame -> list of plain-Python dicts (NaN -> None) ready for the DB."""
    loaded = loaded_at.to_pydatetime()
    return [
        {
            "district_id": int(r.district_id),
            "observed_at": r.observed_at.to_pydatetime(),
            "observed_date": r.observed_date,
            "observed_hour": int(r.observed_hour),
            **{m: _none_if_nan(getattr(r, m)) for m in MEASURES},
            "is_forecast": bool(r.is_forecast),
            "loaded_at": loaded,
        }
        for r in df.itertuples(index=False)
    ]


def load_silver(engine: Engine, df: pd.DataFrame, loaded_at: pd.Timestamp | None = None) -> int:
    """Upsert cleaned rows; re-running never creates duplicates."""
    rows = silver_records(df, loaded_at or now_local())
    n = upsert(engine, "silver_weather_hourly", rows, ["district_id", "observed_at"])
    log.info("Upserted %d rows into silver_weather_hourly", n)
    return n


def load_dim_district(engine: Engine, districts: pd.DataFrame) -> int:
    rows = [
        {
            "district_id": int(r.district_id),
            "district_name": r.district_name,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "region": r.region,
            "area_sq_km": int(r.area_sq_km),
            "hq_city": r.hq_city,
        }
        for r in districts.itertuples(index=False)
    ]
    return upsert(engine, "dim_district", rows, ["district_id"])


def load_dim_date(engine: Engine, start: date, end: date) -> int:
    rows = []
    for d in pd.date_range(start, end, freq="D"):
        rows.append(
            {
                "date_key": int(d.strftime("%Y%m%d")),
                "full_date": d.date(),
                "year": d.year,
                "month": d.month,
                "month_name": d.strftime("%B"),
                "day_of_month": d.day,
                "day_name": d.strftime("%A"),
                "is_weekend": d.dayofweek >= 5,
                "season": SEASONS[d.month],
            }
        )
    return upsert(engine, "dim_date", rows, ["date_key"])


REFRESH_FACT_SQL = """
INSERT INTO fact_weather (
    district_id, observed_at, date_key, hour_of_day,
    temperature_c, humidity_pct, rainfall_mm, wind_speed_kmh,
    pm10, pm2_5, aqi, is_forecast)
SELECT
    s.district_id, s.observed_at, d.date_key, s.observed_hour,
    s.temperature_c, s.humidity_pct, s.rainfall_mm, s.wind_speed_kmh,
    s.pm10, s.pm2_5, s.aqi, s.is_forecast
FROM silver_weather_hourly s
JOIN dim_date d ON d.full_date = s.observed_date
WHERE TRUE
ON CONFLICT (district_id, observed_at) DO UPDATE SET
    date_key       = EXCLUDED.date_key,
    hour_of_day    = EXCLUDED.hour_of_day,
    temperature_c  = EXCLUDED.temperature_c,
    humidity_pct   = EXCLUDED.humidity_pct,
    rainfall_mm    = EXCLUDED.rainfall_mm,
    wind_speed_kmh = EXCLUDED.wind_speed_kmh,
    pm10           = EXCLUDED.pm10,
    pm2_5          = EXCLUDED.pm2_5,
    aqi            = EXCLUDED.aqi,
    is_forecast    = EXCLUDED.is_forecast
"""


def refresh_fact(engine: Engine) -> int:
    """Rebuild/refresh fact_weather from silver (ELT step done in SQL)."""
    with engine.begin() as conn:
        result = conn.execute(text(REFRESH_FACT_SQL))
    log.info("fact_weather refreshed (%s rows touched)", result.rowcount)
    return int(result.rowcount or 0)


def date_span(df: pd.DataFrame, pad_days: int = 1) -> tuple[date, date]:
    """Date range for dim_date, padded so late-night rows always join."""
    return (
        df["observed_date"].min() - timedelta(days=pad_days),
        df["observed_date"].max() + timedelta(days=pad_days),
    )
