"""answer(text) -> Turn. The one code path behind both POST /api/query and the voice proxy,
so typed and spoken answers can never disagree."""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend import events, state
from backend.analysis.summarize import build_bundle
from backend.config import get_settings
from backend.contract import (
    Channel,
    GuardResult,
    Intent,
    Latency,
    NarrationSource,
    Turn,
)
from backend.intent import route
from backend.narration import refusals
from backend.narration.client import narrate

log = logging.getLogger("beacon.service")
DEMO_CACHE = Path("data/demo_cache")
PRECOMPUTE = (Intent.anomalies, Intent.month_summary)
FIXED_ANSWERS = {
    Intent.advice_refused: (refusals.ADVICE, NarrationSource.refusal),
    Intent.help: (refusals.HELP, NarrationSource.template),
    Intent.unknown: (refusals.UNKNOWN, NarrationSource.template),
}


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def compute(intent: Intent, discreet: bool) -> state.CachedAnswer:
    """Analysis + narration for one intent, cached per dataset."""
    hit = state.cached(intent, discreet)
    if hit:
        return hit
    digest = state.state.digest
    t0 = time.perf_counter()
    bundle = build_bundle(state.ledger().df, intent)
    analysis_ms = _ms(t0)
    t1 = time.perf_counter()
    narration = narrate(bundle, discreet)
    answer = state.CachedAnswer(bundle, narration.text, narration.source, narration.guard,
                                analysis_ms, _ms(t1))
    state.store(intent, discreet, answer, digest)
    return answer


def _demo_turn(intent: Intent) -> Turn | None:
    path = DEMO_CACHE / f"{intent.value}.json"
    if not path.exists():
        return None
    turn = Turn.model_validate_json(path.read_text(encoding="utf-8"))
    audio = DEMO_CACHE / f"{intent.value}.mp3"
    return turn.model_copy(update={
        "narration_source": NarrationSource.cache,
        "audio_url": f"/api/demo/audio/{intent.value}.mp3" if audio.exists() else None,
    })


def answer(text: str, channel: Channel = Channel.text, discreet: bool = False) -> Turn:
    start = time.perf_counter()
    intent = route(text)
    bundle = None
    audio_url = None
    guard = GuardResult(passed=True, attempts=0)
    analysis_ms = narration_ms = 0

    if intent == Intent.replay:
        narration = state.state.last_narration or refusals.NOTHING_TO_REPEAT
        source = NarrationSource.replay
    elif intent in FIXED_ANSWERS:
        narration, source = FIXED_ANSWERS[intent]
    elif get_settings().demo_mode and (demo := _demo_turn(intent)) is not None:
        narration, source, bundle, guard, audio_url = (
            demo.narration, demo.narration_source, demo.fact_bundle, demo.guard, demo.audio_url
        )
    else:
        result = compute(intent, discreet)
        narration, source, bundle, guard = (result.narration, result.source, result.bundle,
                                            result.guard)
        analysis_ms, narration_ms = result.analysis_ms, result.narration_ms

    turn = Turn(
        turn_id=str(uuid.uuid4()),
        created_at=datetime.now(UTC),
        channel=channel,
        query_text=text,
        intent=intent,
        narration=narration,
        narration_source=source,
        fact_bundle=bundle,
        guard=guard,
        latency_ms=Latency(analysis=analysis_ms, narration=narration_ms, total=_ms(start)),
        audio_url=audio_url,
    )
    state.state.last_narration = narration
    events.publish_turn(turn)
    return turn


def warm_async() -> None:
    """Precompute the hero answers in the background so the first question is instant."""
    def run() -> None:
        for intent in PRECOMPUTE:
            try:
                compute(intent, discreet=False)
            except Exception:
                log.exception("precompute failed for %s", intent)

    settings = get_settings()
    if settings.precompute and not settings.demo_mode:
        threading.Thread(target=run, name="precompute", daemon=True).start()
