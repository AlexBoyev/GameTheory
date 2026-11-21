"""The ASGI app factory and the composition root's entry point.

Run with `uv run uvicorn app.main:app --reload --port 8000`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import (
    agents,
    events,
    god,
    health,
    llm,
    metrics,
    sim,
    snapshots,
    social,
    tribes,
    world,
)
from app.api.ws import routes as ws_routes
from app.api.ws.hub import WebSocketHub
from app.container import Container, build_container
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings

LOG = get_logger(__name__)

DESCRIPTION = """
Game Theory - an autonomous 3D society simulation (game theory, survival,
manipulation, tribes). Local only, no paid services.
""".strip()

ROUTERS = (
    health.router,
    sim.router,
    world.router,
    agents.router,
    tribes.router,
    social.router,
    metrics.router,
    events.router,
    snapshots.router,
    llm.router,
    god.router,
)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Overrides the environment-derived settings (used by tests).
        container: Pre-wired services; built from `settings` when omitted.
    """
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Start services, attach the WS hub to the broadcast loop, then clean up."""
        hub = WebSocketHub()
        application.state.hub = hub
        resolved_container.simulation.subscribe(hub.broadcast)
        await resolved_container.startup()
        try:
            yield
        finally:
            resolved_container.simulation.unsubscribe(hub.broadcast)
            await resolved_container.shutdown()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    application.state.container = resolved_container
    application.state.hub = WebSocketHub()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in ROUTERS:
        application.include_router(router, prefix="/api")
    application.include_router(ws_routes.router)

    LOG.info(
        "app.created",
        env=resolved_settings.env,
        llm_provider=resolved_settings.llm_provider,
        seed=resolved_settings.sim_seed,
    )
    return application


app = create_app()
