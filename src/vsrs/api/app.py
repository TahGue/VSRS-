"""FastAPI application factory for VSRS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vsrs.api.routes import router
from vsrs.core.logging import get_logger

logger = get_logger("api.app")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="VSRS API",
        description="Verified Software Reasoning System - evidence-grounded coding reasoning and verification platform",
        version="0.1.0",
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    logger.info("VSRS API app created")
    return app


app = create_app()
