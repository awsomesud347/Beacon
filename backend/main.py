from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Beacon API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()
