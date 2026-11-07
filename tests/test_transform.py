from __future__ import annotations

import numpy as np
import pandas as pd

from ingestion.transform import SILVER_COLUMNS, build_silver_frame, clean, payload_to_frame
from tests.factories import NOW, RUN_DATE, weather_payload


def test_builds_full_hourly_frame(bronze_dir, districts):
    df = build_silver_frame(bronze_dir, RUN_DATE, districts, NOW)
    assert list(df.columns) == SILVER_COLUMNS
    assert len(df) == 14 * 192
    assert df["district_id"].nunique() == 14
    assert not df.duplicated(["district_id", "observed_at"]).any()
    assert df["observed_at"].dt.tz is None  # tz-naive IST


def test_forecast_flag_splits_at_current_hour(bronze_dir, districts):
    df = build_silver_frame(bronze_dir, RUN_DATE, districts, NOW)
    one = df[df.district_id == 1]
    assert one.loc[~one.is_forecast, "observed_at"].max() == pd.Timestamp("2026-10-24 14:00")
    assert one.is_forecast.sum() == 9   # 15:00 .. 23:00


def test_utc_payload_is_shifted_to_ist():
    p = weather_payload(1)
    p["utc_offset_seconds"] = 0
    p["hourly"]["time"][0] = "2026-10-17T00:00"
    df = payload_to_frame({"payload": p}, 1)
    assert df["observed_at"].iloc[0] == pd.Timestamp("2026-10-17 05:30")


def test_clean_removes_duplicates_and_coerces_bad_numbers():
    raw = pd.DataFrame({
        "district_id": [1, 1, 1],
        "observed_at": pd.to_datetime(["2026-10-20 01:00"] * 2 + ["2026-10-20 02:00"]),
        "temperature_c": [20.0, 21.0, "n/a"],
    })
    out = clean(raw, NOW)
    assert len(out) == 2
    assert out.loc[out.observed_at == "2026-10-20 01:00", "temperature_c"].iloc[0] == 21.0  # keeps last
    assert np.isnan(out.loc[out.observed_at == "2026-10-20 02:00", "temperature_c"].iloc[0])
    assert {"humidity_pct", "aqi"} <= set(out.columns)  # missing measures become NaN columns


def test_missing_air_quality_file_yields_null_aqi(bronze_dir, districts):
    (bronze_dir / "2026-10-24" / "kollam_air_quality.json").unlink()
    df = build_silver_frame(bronze_dir, RUN_DATE, districts, NOW)
    kollam = df[df.district_id == 2]
    assert len(kollam) == 192 and kollam["aqi"].isna().all()


def test_empty_bronze_returns_empty_frame(tmp_path, districts):
    df = build_silver_frame(tmp_path, RUN_DATE, districts, NOW)
    assert df.empty and list(df.columns) == SILVER_COLUMNS
