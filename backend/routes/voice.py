from fastapi import APIRouter

from backend import stub
from backend.config import get_settings
from backend.contract import VoiceSession
from backend.errors import not_implemented

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/session", response_model=VoiceSession)
def voice_session() -> VoiceSession:
    if get_settings().stub_mode:
        return stub.voice_session()
    raise not_implemented("voice session")
