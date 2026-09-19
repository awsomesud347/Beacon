from fastapi import APIRouter

from backend import stub
from backend.config import get_settings
from backend.contract import ApiError, VoiceSession
from backend.voice import elevenlabs

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get(
    "/session",
    response_model=VoiceSession,
    responses={502: {"model": ApiError}, 503: {"model": ApiError}},
)
def voice_session() -> VoiceSession:
    if get_settings().stub_mode:
        return stub.voice_session()
    return elevenlabs.signed_url()
