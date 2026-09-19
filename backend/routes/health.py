from fastapi import APIRouter

from backend import state, stub
from backend.config import get_settings
from backend.contract import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    s = get_settings()
    dataset = stub.dataset() if s.stub_mode else state.dataset_info()
    return Health(narrator=s.narrator, demo_mode=s.demo_mode, stub_mode=s.stub_mode,
                  dataset=dataset)
