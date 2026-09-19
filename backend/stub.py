"""STUB_MODE=1 handlers: canned responses from contract/examples so the frontend can build
against the real API shape before analysis/narration exist."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend import events
from backend.config import get_settings
from backend.contract import Channel, DatasetInfo, Turn, VoiceSession

_EXAMPLES = Path(__file__).resolve().parent.parent / "contract" / "examples"

_ROUTES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(should|advice|afford|invest|recommend)\b", re.I), "turn_refusal.json"),
    (re.compile(r"unusual|weird|strange|odd|anomal", re.I), "turn_anomalies.json"),
    (re.compile(r"how am i|how.*doing|this month|summary|where.*money", re.I), "turn_summary.json"),
]


def query(text: str, channel: Channel) -> Turn:
    name = next((f for pattern, f in _ROUTES if pattern.search(text)), "turn_unknown.json")
    turn = Turn.model_validate_json((_EXAMPLES / name).read_text()).model_copy(
        update={
            "turn_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC),
            "channel": channel,
            "query_text": text,
        }
    )
    events.publish_turn(turn)
    return turn


def dataset() -> DatasetInfo:
    return DatasetInfo.model_validate_json((_EXAMPLES / "dataset_info.json").read_text())


def uploaded_dataset(filename: str) -> DatasetInfo:
    info = dataset().model_copy(update={"source": "upload", "name": filename})
    events.publish_dataset(info)
    return info


def reset_dataset() -> DatasetInfo:
    info = dataset()
    events.publish_dataset(info)
    return info


def voice_session() -> VoiceSession:
    session = VoiceSession.model_validate_json((_EXAMPLES / "voice_session.json").read_text())
    agent_id = get_settings().elevenlabs_agent_id
    return session.model_copy(update={"agent_id": agent_id}) if agent_id else session
