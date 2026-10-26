"""
verify_stage1.py – Quick smoke-test for Stage 1 setup.
Run:  python verify_stage1.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REQUIRED_DIRS = [
    "ingestion",
    "sql",
    "api",
    "tests",
    "data/bronze",
    "data/silver",
    "data/gold",
]

REQUIRED_FILES = [
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "districts.csv",
    "config.py",
    "ingestion/__init__.py",
    "ingestion/logger.py",
]

REQUIRED_DISTRICTS = 14


def check_dirs() -> list[str]:
    errors: list[str] = []
    for d in REQUIRED_DIRS:
        if not Path(d).is_dir():
            errors.append(f"  ✗ Missing directory: {d}")
        else:
            print(f"  ✓ {d}/")
    return errors


def check_files() -> list[str]:
    errors: list[str] = []
    for f in REQUIRED_FILES:
        if not Path(f).exists():
            errors.append(f"  ✗ Missing file: {f}")
        else:
            print(f"  ✓ {f}")
    return errors


def check_districts() -> list[str]:
    errors: list[str] = []
    csv_path = Path("districts.csv")
    if not csv_path.exists():
        return [f"  ✗ districts.csv not found"]
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if len(rows) != REQUIRED_DISTRICTS:
        errors.append(
            f"  ✗ Expected {REQUIRED_DISTRICTS} districts, found {len(rows)}"
        )
    else:
        print(f"  ✓ districts.csv has {len(rows)} rows")

    # Validate lat/long present and numeric
    for row in rows:
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            assert 8.0 <= lat <= 13.0, f"Unexpected latitude {lat}"
            assert 74.0 <= lon <= 78.0, f"Unexpected longitude {lon}"
        except (KeyError, ValueError, AssertionError) as exc:
            errors.append(f"  ✗ Bad lat/lon for {row.get('district_name')}: {exc}")
    if not errors:
        print("  ✓ All lat/long values are within Kerala bounding box")
    return errors


def check_config_import() -> list[str]:
    errors: list[str] = []
    try:
        from config import settings  # noqa: F401

        print(f"  ✓ config.settings loaded (tz={settings.timezone})")
    except Exception as exc:
        errors.append(f"  ✗ config import failed: {exc}")
    return errors


def main() -> None:
    print("\n━━━━━━━━━━━━  Kerala Climate Pulse — Stage 1 Verification  ━━━━━━━━━━━━\n")
    all_errors: list[str] = []

    print("📁  Directories:")
    all_errors += check_dirs()

    print("\n📄  Files:")
    all_errors += check_files()

    print("\n🗺️   Districts CSV:")
    all_errors += check_districts()

    print("\n⚙️   Config import:")
    all_errors += check_config_import()

    print()
    if all_errors:
        print("❌  STAGE 1 FAILED — fix the issues below:\n")
        print("\n".join(all_errors))
        sys.exit(1)
    else:
        print("✅  STAGE 1 PASSED — all checks green!\n")


if __name__ == "__main__":
    main()
