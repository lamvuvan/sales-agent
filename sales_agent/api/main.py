"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..db.neo4j_client import close_driver
from ..logging import configure_logging
from .routes_health import router as health_router
from .routes_prescription import router as rx_router
from .routes_symptom import router as sym_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    configure_logging()
    yield
    close_driver()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pharmacy Sales Agent",
        version="0.1.0",
        description="Trợ lý AI cho nhân viên nhà thuốc / tạp hoá (tiếng Việt).",
        lifespan=_lifespan,
    )
    app.include_router(health_router)
    app.include_router(rx_router)
    app.include_router(sym_router)
    return app


app = create_app()
