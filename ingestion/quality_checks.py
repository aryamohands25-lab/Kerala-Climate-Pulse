"""quality_checks.py – Data quality gate between bronze and silver.

Each check returns PASS / WARN / FAIL. Any FAIL is *critical* and stops the
pipeline before bad data reaches silver. A markdown report is always written.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.constants import MEASURE_COLUMNS, VALUE_RANGES
from ingestion.logger import get_logger
from ingestion.timeutil import now_local

log = get_logger(__name__)

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

# Thresholds (percent of values / hours)
NULL_WARN_PCT = 5.0
NULL_FAIL_PCT = 30.0
RANGE_WARN_PCT = 0.0   # any violation warns
RANGE_FAIL_PCT = 5.0
GAP_WARN_PCT = 0.0
GAP_FAIL_PCT = 5.0
FRESH_WARN_HOURS = 6
FRESH_FAIL_HOURS = 24


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)
    rows: int = 0
    generated_at: pd.Timestamp = field(default_factory=now_local)

    def add(self, name: str, status: str, detail: str) -> None:
        self.results.append(CheckResult(name, status, detail))
        log.log(
            40 if status == FAIL else 30 if status == WARN else 20,
            "DQ %-22s %-4s %s", name, status, detail,
        )

    @property
    def has_critical(self) -> bool:
        return any(r.status == FAIL for r in self.results)

    @property
    def overall(self) -> str:
        if self.has_critical:
            return FAIL
        return WARN if any(r.status == WARN for r in self.results) else PASS

    def to_markdown(self) -> str:
        icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌"}
        lines = [
            "# Data Quality Report",
            "",
            f"- Generated: {self.generated_at:%Y-%m-%d %H:%M} IST",
            f"- Rows checked: {self.rows:,}",
            f"- Overall: {icon[self.overall]} **{self.overall}**",
            "",
            "| Check | Status | Detail |",
            "|---|---|---|",
        ]
        lines += [f"| {r.name} | {icon[r.status]} {r.status} | {r.detail} |" for r in self.results]
        return "\n".join(lines) + "\n"


def _grade(pct: float, warn_at: float, fail_at: float) -> str:
    if pct > fail_at:
        return FAIL
    return WARN if pct > warn_at else PASS


def check_row_count(df: pd.DataFrame, rep: QualityReport) -> None:
    rep.add("row_count", PASS if len(df) else FAIL, f"{len(df):,} rows")


def check_district_coverage(df: pd.DataFrame, expected: set[int], rep: QualityReport) -> None:
    present = set(df["district_id"].unique()) if len(df) else set()
    missing = sorted(expected - present)
    rep.add(
        "district_coverage",
        FAIL if missing else PASS,
        f"{len(present)}/{len(expected)} districts" + (f"; missing ids {missing}" if missing else ""),
    )


def check_duplicates(df: pd.DataFrame, rep: QualityReport) -> None:
    dups = int(df.duplicated(subset=["district_id", "observed_at"]).sum()) if len(df) else 0
    rep.add("duplicate_keys", FAIL if dups else PASS, f"{dups} duplicate (district, hour) keys")


def check_missing_hours(df: pd.DataFrame, rep: QualityReport) -> None:
    if df.empty:
        return
    missing = expected = 0
    for _, g in df.groupby("district_id"):
        span = int((g["observed_at"].max() - g["observed_at"].min()) / pd.Timedelta(hours=1)) + 1
        expected += span
        missing += span - g["observed_at"].nunique()
    pct = 100 * missing / expected if expected else 0.0
    rep.add(
        "missing_timestamps",
        _grade(pct, GAP_WARN_PCT, GAP_FAIL_PCT),
        f"{missing} missing hourly slots of {expected} expected ({pct:.2f}%)",
    )


def check_nulls(df: pd.DataFrame, rep: QualityReport) -> None:
    observed = df[~df["is_forecast"]] if len(df) else df
    for col in MEASURE_COLUMNS:
        pct = 100 * float(observed[col].isna().mean()) if len(observed) else 100.0
        rep.add(f"nulls:{col}", _grade(pct, NULL_WARN_PCT, NULL_FAIL_PCT), f"{pct:.1f}% null (observed hours)")


def range_violations(df: pd.DataFrame) -> dict[str, int]:
    out: dict[str, int] = {}
    for col, (lo, hi) in VALUE_RANGES.items():
        s = df[col]
        out[col] = int(((s < lo) | (s > hi)).sum())
    return out


def check_ranges(df: pd.DataFrame, rep: QualityReport) -> None:
    for col, bad in range_violations(df).items():
        lo, hi = VALUE_RANGES[col]
        total = int(df[col].notna().sum())
        pct = 100 * bad / total if total else 0.0
        rep.add(f"range:{col}", _grade(pct, RANGE_WARN_PCT, RANGE_FAIL_PCT), f"{bad} of {total} outside [{lo}, {hi}]")


def check_freshness(df: pd.DataFrame, rep: QualityReport, now: pd.Timestamp) -> None:
    observed = df[~df["is_forecast"]] if len(df) else df
    if observed.empty:
        rep.add("freshness", FAIL, "no observed (non-forecast) rows")
        return
    age_h = (now - observed["observed_at"].max()) / pd.Timedelta(hours=1)
    status = FAIL if age_h > FRESH_FAIL_HOURS else WARN if age_h > FRESH_WARN_HOURS else PASS
    rep.add("freshness", status, f"latest observed hour is {age_h:.1f}h old")


def run_checks(
    df: pd.DataFrame,
    expected_district_ids: set[int],
    now: pd.Timestamp | None = None,
) -> QualityReport:
    """Run every check and return the report (does not raise)."""
    now = now if now is not None else now_local()
    rep = QualityReport(rows=len(df), generated_at=now)
    check_row_count(df, rep)
    if len(df):
        check_district_coverage(df, expected_district_ids, rep)
        check_duplicates(df, rep)
        check_missing_hours(df, rep)
        check_nulls(df, rep)
        check_ranges(df, rep)
    check_freshness(df, rep, now)
    return rep


def quarantine_out_of_range(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Set physically impossible values to NULL (kept out of silver)."""
    df = df.copy()
    total = 0
    for col, (lo, hi) in VALUE_RANGES.items():
        bad = (df[col] < lo) | (df[col] > hi)
        total += int(bad.sum())
        df.loc[bad, col] = np.nan
    return df, total


def write_report(rep: QualityReport, reports_dir: Path = Path("reports")) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"quality_report_{stamp}.md"
    md = rep.to_markdown()
    path.write_text(md, encoding="utf-8")
    (reports_dir / "quality_report_latest.md").write_text(md, encoding="utf-8")
    return path
