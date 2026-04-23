"""Create / verify Postgres + Neo4j schema (idempotent)."""

from __future__ import annotations

from sqlalchemy import text

from .models import Base
from .neo4j_client import ensure_schema as ensure_neo4j_schema
from .pg import get_engine


def ensure_pg_schema() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    Base.metadata.create_all(engine)


def ensure_all() -> None:
    ensure_pg_schema()
    ensure_neo4j_schema()
