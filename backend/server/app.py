from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .routers import auth, sync, metrics, matches, health
from .routers import gis as gis_router
from .routers import live as live_router
from .routers import assets
from .cron.sweeper import start_sweeper
from .cron.ingestor import start_ingestor


def create_app() -> FastAPI:
    app = FastAPI(title="LoL Stat-Tracker", version="1.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(auth.config_router, prefix="/api", tags=["config"])
    app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
    app.include_router(metrics.router, prefix="/api", tags=["metrics"])
    app.include_router(matches.router, prefix="/api", tags=["matches"])
    app.include_router(gis_router.router, prefix="/api", tags=["gis"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(live_router.router, prefix="/api/live", tags=["live"])  # /api/live/status
    app.include_router(assets.router, tags=["assets"])  # /assets/*

    # WebSocket route for live under /ws defined in router module
    from .live.socket import register_ws
    
    register_ws(app)
    # Background sweeper for precomputing advanced metrics (hourly, low-power)
    try:
        start_sweeper()
    except Exception:
        # Non-fatal if sweeper fails to start
        pass
    # Background ingestor for new matches (every 5 minutes)
    try:
        start_ingestor()
    except Exception:
        pass

    # Global error handler → uniform envelope
    @app.exception_handler(Exception)
    async def on_error(request: Request, exc: Exception):
        return JSONResponse({"ok": False, "error": {"code": "INTERNAL", "message": str(exc)}}, status_code=500, headers={"Cache-Control": "no-store"})

    # Add Cache-Control no-store for API responses
    @app.middleware("http")
    async def no_store_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Static files (production): serve frontend/dist if available
    dist_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return app


app = create_app()
