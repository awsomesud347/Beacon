from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.contract import ErrorCode, Intent
from backend.errors import ApiException

router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_CACHE = Path("data/demo_cache")


@router.get(
    "/audio/{intent}.mp3",
    response_class=FileResponse,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
def demo_audio(intent: Intent) -> FileResponse:
    path = DEMO_CACHE / f"{intent.value}.mp3"
    if not get_settings().demo_mode or not path.exists():
        raise ApiException(404, ErrorCode.not_found, f"No cached audio for {intent.value}")
    return FileResponse(path, media_type="audio/mpeg")
