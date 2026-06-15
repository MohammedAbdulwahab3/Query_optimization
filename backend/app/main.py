"""FastAPI application entrypoint.

On startup it initialises the database, creates the schema, and (optionally)
seeds sample data if the tables are empty. It serves the JSON analytics API
under ``/api`` and the static dashboard at ``/``.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import get_db, init_db
from .routers import analytics
from .schema import init_schema
from .seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

settings = get_settings()

# Resolve the frontend directory relative to the repo root (two levels up).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND_DIR = os.path.join(_REPO_ROOT, settings.frontend_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = init_db(settings)
    logger.info("Using ClickHouse backend: %s", settings.ch_backend)
    init_schema(db)
    if settings.auto_seed:
        result = seed_all(db, settings)
        logger.info("Startup seed: %s", result)
    yield
    db.close()


app = FastAPI(
    title="ClickHouse E-commerce Analytics",
    description="Optimized ClickHouse analytics served as individual FastAPI endpoints.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics.router)


@app.get("/api/health")
def health() -> dict:
    db = get_db()
    rows = db.query("SELECT 1 AS ok")
    return {"status": "ok", "backend": settings.ch_backend, "db": bool(rows)}


@app.post("/api/admin/reseed")
def reseed() -> dict:
    """Wipe and regenerate sample data (handy for demos)."""
    db = get_db()
    init_schema(db)
    return seed_all(db, settings, force=True)


# --- static frontend -------------------------------------------------------- #
if os.path.isdir(FRONTEND_DIR):
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
else:  # pragma: no cover
    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)
