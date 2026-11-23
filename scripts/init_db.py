"""Create the TicketDesk tables.

PostgreSQL (local or RDS): runs sql/schema.sql.
SQLite (quick local trial only): creates tables from the ORM models.

Usage, from the repository root:  python -m scripts.init_db
"""
from __future__ import annotations

import sys
from pathlib import Path

from app import models  # noqa: F401  (registers the tables on Base)
from app.config import Settings
from app.db import Base, build_engine

SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main() -> int:
    engine = build_engine(Settings.from_env())
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for stmt in statements(SCHEMA.read_text()):
                conn.exec_driver_sql(stmt)
        print(f"Schema applied from {SCHEMA.name} ({engine.url.host}/{engine.url.database})")
    else:
        Base.metadata.create_all(engine)
        print(f"Tables created on {engine.dialect.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
