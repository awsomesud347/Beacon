from fastapi import APIRouter

from backend.contract import VoiceSession
from backend.errors import not_implemented

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/session", response_model=VoiceSession)
def voice_session() -> VoiceSession:
    raise not_implemented("voice session")
