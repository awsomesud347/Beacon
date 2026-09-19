from fastapi import APIRouter

from backend.config import get_settings
from backend.contract import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    s = get_settings()
    return Health(narrator=s.narrator, demo_mode=s.demo_mode, stub_mode=s.stub_mode)
