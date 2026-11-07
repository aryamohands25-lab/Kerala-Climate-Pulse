"""db.py – Engine creation, SQL-file runner, and portable upsert helper."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.engine import Engine

from config import settings
from ingestion.logger import get_logger

log = get_logger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
SQL_FILES = ["01_silver.sql", "02_gold.sql", "03_views.sql"]


def get_engine(url: str | None = None) -> Engine:
    """Create an engine from an explicit URL or from settings."""
    return create_engine(url or settings.database_url, pool_pre_ping=True, future=True)


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script on ';' after stripping '--' comments."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    cleaned = re.sub(r"--[^\n]*", "", "\n".join(lines))
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def run_sql_file(engine: Engine, path: Path) -> int:
    """Execute every statement in a .sql file inside one transaction."""
    statements = _split_statements(path.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    return len(statements)


def init_schema(engine: Engine) -> None:
    """Create silver tables, gold tables, and views (idempotent)."""
    for name in SQL_FILES:
        n = run_sql_file(engine, SQL_DIR / name)
        log.info("Applied %s (%d statements)", name, n)


def reflect(engine: Engine, name: str) -> Table:
    """Reflect an existing table so inserts use the real column types."""
    return Table(name, MetaData(), autoload_with=engine)


def upsert(
    engine: Engine,
    table_name: str,
    rows: Sequence[dict[str, Any]],
    key_columns: Iterable[str],
    chunk_size: int = 5000,
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE for PostgreSQL (and SQLite for tests)."""
    if not rows:
        return 0
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"Unsupported dialect {engine.dialect.name}")

    table = reflect(engine, table_name)
    keys = list(key_columns)
    update_cols = [c for c in rows[0] if c not in keys]
    stmt = insert(table)
    stmt = stmt.on_conflict_do_update(
        index_elements=keys, set_={c: stmt.excluded[c] for c in update_cols}
    )
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk_size):
            conn.execute(stmt, list(rows[i : i + chunk_size]))
    return len(rows)
