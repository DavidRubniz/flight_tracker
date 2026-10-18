"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from flight_tracker.api.container import Container
from flight_tracker.api.routes import router
from flight_tracker.config import STATIC_DIR, Config, get_config

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None, *, start_scheduler: bool = True) -> FastAPI:
    resolved = config or get_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container.build(resolved)
        app.state.container = container
        if start_scheduler:
            container.start()
        logger.info(
            "Provider: %s · origin %s · currency %s",
            container.provider.name,
            resolved.origin_airport,
            resolved.currency,
        )
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(title="Flight Price Tracker", version="1.0.0", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
