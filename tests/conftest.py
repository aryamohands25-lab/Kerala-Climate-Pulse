from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from tests.factories import write_bronze

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def districts() -> pd.DataFrame:
    return pd.read_csv(ROOT / "districts.csv")


@pytest.fixture()
def bronze_dir(tmp_path, districts) -> Path:
    d = tmp_path / "bronze"
    write_bronze(d, districts)
    return d


@pytest.fixture()
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    yield engine
    engine.dispose()
