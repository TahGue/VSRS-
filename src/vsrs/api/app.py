"""FastAPI application factory for VSRS."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from vsrs.api.routes import router
from vsrs.api.enterprise_routes import router as enterprise_router
from vsrs.api.websocket import manager as ws_manager
from vsrs.core.logging import get_logger

logger = get_logger("api.app")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="VSRS API",
        description="Verified Software Reasoning System - evidence-grounded coding reasoning and verification platform",
        version="2.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")
    app.include_router(enterprise_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws/runs/{run_id}")
    async def websocket_run(websocket: WebSocket, run_id: str) -> None:
        """WebSocket endpoint for real-time run progress updates."""
        await ws_manager.connect(run_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text('{"type": "pong"}')
        except WebSocketDisconnect:
            await ws_manager.disconnect(run_id, websocket)

    # Serve the web dashboard (built React app) if it exists
    dashboard_dist = Path(__file__).resolve().parent.parent.parent.parent / "web-dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/assets", StaticFiles(directory=dashboard_dist / "assets"), name="assets")

        @app.get("/")
        async def dashboard_root() -> FileResponse:
            return FileResponse(dashboard_dist / "index.html")

        @app.get("/runs/{run_id}")
        async def dashboard_run() -> FileResponse:
            return FileResponse(dashboard_dist / "index.html")

        @app.get("/benchmarks")
        async def dashboard_benchmarks() -> FileResponse:
            return FileResponse(dashboard_dist / "index.html")

        @app.get("/settings")
        async def dashboard_settings() -> FileResponse:
            return FileResponse(dashboard_dist / "index.html")

        logger.info(f"Web dashboard served from {dashboard_dist}")

    logger.info("VSRS API app created")
    return app


app = create_app()
