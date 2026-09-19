import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import service, state
from backend.config import get_settings
from backend.contract import CONTRACT_VERSION, SseEvent
from backend.errors import install_error_handlers
from backend.routes import dataset, demo, events, health, llm_proxy, query, voice


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.stub_mode:
        state.load_default()
        service.warm_async()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Beacon API", version=CONTRACT_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for module in (health, query, dataset, events, voice, demo, llm_proxy):
        app.include_router(module.router)
    _extend_openapi(app)
    return app


def _extend_openapi(app: FastAPI) -> None:
    """Add schemas that no route references directly (SSE event names)."""
    base = app.openapi

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = base()
        schema["components"]["schemas"]["SseEvent"] = {
            "title": "SseEvent",
            "type": "string",
            "enum": [e.value for e in SseEvent],
        }
        return schema

    app.openapi = openapi


app = create_app()
