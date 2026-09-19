"""ElevenLabs REST calls. The API key lives here and never reaches the browser."""

import httpx

from backend.config import get_settings
from backend.contract import ErrorCode, VoiceSession
from backend.errors import ApiException

BASE_URL = "https://api.elevenlabs.io/v1"
TIMEOUT_S = 10.0


def _headers() -> dict[str, str]:
    key = get_settings().elevenlabs_api_key
    if not key:
        raise ApiException(503, ErrorCode.not_implemented, "ELEVENLABS_API_KEY is not set")
    return {"xi-api-key": key}


def signed_url() -> VoiceSession:
    """Short-lived credential the browser uses to open the agent conversation."""
    agent_id = get_settings().elevenlabs_agent_id
    if not agent_id:
        raise ApiException(503, ErrorCode.not_implemented, "ELEVENLABS_AGENT_ID is not set")
    try:
        r = httpx.get(
            f"{BASE_URL}/convai/conversation/get-signed-url",
            params={"agent_id": agent_id},
            headers=_headers(),
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiException(
            502, ErrorCode.not_found, "Could not start a voice session with ElevenLabs", [str(exc)]
        ) from exc
    return VoiceSession(agent_id=agent_id, signed_url=r.json()["signed_url"])


def text_to_speech(text: str, voice_id: str | None = None) -> bytes:
    """Used by scripts/presynth_demo.py to build the offline demo cache."""
    s = get_settings()
    voice = voice_id or s.elevenlabs_voice_id
    if not voice:
        raise ApiException(503, ErrorCode.not_implemented, "ELEVENLABS_VOICE_ID is not set")
    r = httpx.post(
        f"{BASE_URL}/text-to-speech/{voice}",
        headers=_headers(),
        json={"text": text, "model_id": "eleven_flash_v2"},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.content
