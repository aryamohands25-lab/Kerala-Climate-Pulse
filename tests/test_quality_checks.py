from __future__ import annotations

import numpy as np
import pandas as pd

from ingestion.quality_checks import FAIL, PASS, WARN, quarantine_out_of_range, run_checks
from ingestion.transform import build_silver_frame
from tests.factories import NOW, RUN_DATE, write_bronze

IDS = set(range(1, 15))


def _frame(bronze_dir, districts):
    return build_silver_frame(bronze_dir, RUN_DATE, districts, NOW)


def _status(rep, name):
    return next(r.status for r in rep.results if r.name == name)


def test_clean_data_passes(bronze_dir, districts):
    rep = run_checks(_frame(bronze_dir, districts), IDS, NOW)
    assert rep.overall == PASS and not rep.has_critical


def test_missing_district_is_critical(tmp_path, districts):
    write_bronze(tmp_path, districts, skip_district_ids=(3,))
    rep = run_checks(_frame(tmp_path, districts), IDS, NOW)
    assert _status(rep, "district_coverage") == FAIL and rep.has_critical


def test_duplicate_keys_are_critical(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    df = pd.concat([df, df.head(3)], ignore_index=True)
    assert _status(run_checks(df, IDS, NOW), "duplicate_keys") == FAIL


def test_missing_hours_are_detected(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    df = df.drop(df[(df.district_id == 1) & (df.observed_hour.isin([3, 4]))].index[:2])
    rep = run_checks(df, IDS, NOW)
    assert _status(rep, "missing_timestamps") == WARN
    assert "2 missing" in next(r.detail for r in rep.results if r.name == "missing_timestamps")


def test_small_range_violation_warns_large_fails(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    df.loc[0, "humidity_pct"] = 140
    assert _status(run_checks(df, IDS, NOW), "range:humidity_pct") == WARN
    df.loc[: int(len(df) * 0.1), "humidity_pct"] = 140
    assert _status(run_checks(df, IDS, NOW), "range:humidity_pct") == FAIL


def test_null_threshold(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    obs = df.index[~df.is_forecast]
    df.loc[obs[: int(len(obs) * 0.10)], "aqi"] = np.nan
    assert _status(run_checks(df, IDS, NOW), "nulls:aqi") == WARN
    df.loc[obs[: int(len(obs) * 0.5)], "aqi"] = np.nan
    assert _status(run_checks(df, IDS, NOW), "nulls:aqi") == FAIL


def test_stale_data_fails_freshness(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    rep = run_checks(df, IDS, NOW + pd.Timedelta(days=3))
    assert _status(rep, "freshness") == FAIL


def test_empty_frame_is_critical(districts):
    rep = run_checks(pd.DataFrame(columns=["district_id", "observed_at", "is_forecast"]), IDS, NOW)
    assert rep.has_critical


def test_quarantine_nulls_only_bad_values(bronze_dir, districts):
    df = _frame(bronze_dir, districts)
    df.loc[5, "temperature_c"] = 99
    df.loc[6, "rainfall_mm"] = -3
    fixed, n = quarantine_out_of_range(df)
    assert n == 2 and np.isnan(fixed.loc[5, "temperature_c"]) and np.isnan(fixed.loc[6, "rainfall_mm"])
    assert fixed.loc[7, "temperature_c"] == df.loc[7, "temperature_c"]


def test_markdown_report_contains_every_check(bronze_dir, districts):
    md = run_checks(_frame(bronze_dir, districts), IDS, NOW).to_markdown()
    for name in ("row_count", "district_coverage", "duplicate_keys", "freshness", "range:aqi"):
        assert name in md
