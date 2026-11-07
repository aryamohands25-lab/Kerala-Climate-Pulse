"""factories.py – Build synthetic Open-Meteo-shaped payloads for offline tests.

The numbers are made up; the *structure* mirrors the real API responses.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.ingest import bronze_path

NOW = pd.Timestamp("2026-10-24 14:30")          # pretend "current" IST time
RUN_DATE = date(2026, 10, 24)
START = pd.Timestamp("2026-10-17 00:00")        # past_days=7
END = pd.Timestamp("2026-10-24 23:00")          # forecast_days=1
HOURS = pd.date_range(START, END, freq="h")     # 192 hours
HEAVY_RAIN_DISTRICT = 6    # Idukki, on 2026-10-23
POOR_AQI_DISTRICT = 7      # Ernakulam, on 2026-10-23


def _times(hours=HOURS) -> list[str]:
    return [t.strftime("%Y-%m-%dT%H:%M") for t in hours]


def weather_payload(district_id: int, hours=HOURS) -> dict:
    rng = np.random.default_rng(district_id)
    n = len(hours)
    hod = np.array([t.hour for t in hours])
    rain = rng.choice([0.0, 0.0, 0.0, 0.2, 0.5, 1.0], size=n)
    if district_id == HEAVY_RAIN_DISTRICT:
        heavy = np.array([(t.date() == date(2026, 10, 23)) and 12 <= t.hour <= 19 for t in hours])
        rain = np.where(heavy, 10.0, rain)   # 8 h x 10 mm = 80 mm
    return {
        "latitude": 10.0, "longitude": 76.0, "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly": {
            "time": _times(hours),
            "temperature_2m": list(np.round(26 + 4 * np.sin((hod - 9) / 24 * 2 * np.pi) + rng.normal(0, .3, n), 1)),
            "relative_humidity_2m": list(np.round(rng.uniform(70, 95, n), 0)),
            "precipitation": list(rain),
            "wind_speed_10m": list(np.round(rng.uniform(5, 20, n), 1)),
        },
    }


def air_payload(district_id: int, hours=HOURS) -> dict:
    rng = np.random.default_rng(100 + district_id)
    n = len(hours)
    aqi = np.round(rng.uniform(25, 85, n), 0)
    if district_id == POOR_AQI_DISTRICT:
        peak = np.array([(t.date() == date(2026, 10, 23)) and t.hour == 20 for t in hours])
        aqi = np.where(peak, 120.0, aqi)
    return {
        "latitude": 10.0, "longitude": 76.0, "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly": {
            "time": _times(hours),
            "pm10": list(np.round(rng.uniform(20, 60, n), 1)),
            "pm2_5": list(np.round(rng.uniform(10, 40, n), 1)),
            "us_aqi": list(aqi),
        },
    }


def write_bronze(bronze_dir: Path, districts: pd.DataFrame, *, skip_district_ids=(), mutate=None) -> None:
    """Write weather + air files for every district. `mutate(kind, id, payload)` may edit payloads."""
    for _, row in districts.iterrows():
        did = int(row["district_id"])
        if did in skip_district_ids:
            continue
        for kind, payload in (("weather", weather_payload(did)), ("air_quality", air_payload(did))):
            if mutate:
                mutate(kind, did, payload)
            path = bronze_path(bronze_dir, RUN_DATE, row["district_name"], kind)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"_meta": {"district_id": did}, "payload": payload}), "utf-8")
