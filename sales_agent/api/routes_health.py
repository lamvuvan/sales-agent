"""Health + readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..db.neo4j_client import get_driver
from ..db.pg import session_scope

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    pg_ok = False
    neo_ok = False
    try:
        with session_scope() as sess:
            sess.execute(text("SELECT 1"))
        pg_ok = True
    except Exception:
        pg_ok = False
    try:
        with get_driver().session() as s:
            s.run("RETURN 1").consume()
        neo_ok = True
    except Exception:
        neo_ok = False
    return {
        "postgres": "ok" if pg_ok else "down",
        "neo4j": "ok" if neo_ok else "down",
    }
