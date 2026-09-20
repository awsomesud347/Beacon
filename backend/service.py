"""answer(text) -> Turn. The one code path behind both POST /api/query and the voice proxy,
so typed and spoken answers can never disagree.

The model understands the question (backend/narration/planner.py); pandas computes every
figure; the guard checks every figure before it is spoken. A failed or unusable plan falls
back to an overview answer rather than a dead end — mid-demo, silence is worse than general.
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend import events, safety, state, transcript
from backend.analysis.query import understood_phrase
from backend.analysis.summarize import build_lookup_bundle
from backend.config import get_settings
from backend.contract import (
    Channel,
    GuardResult,
    Intent,
    Latency,
    Metric,
    NarrationSource,
    PeriodKind,
    PlanSource,
    QueryPlan,
    Turn,
)
from backend.narration import planner, refusals
from backend.narration.client import narrate

log = logging.getLogger("beacon.service")
DEMO_CACHE = Path("data/demo_cache")
HISTORY_TURNS = 3
FIXED_ANSWERS = {
    Intent.advice_refused: (refusals.ADVICE, NarrationSource.refusal),
    Intent.identity: (refusals.IDENTITY, NarrationSource.refusal),
    Intent.help: (refusals.HELP, NarrationSource.template),
}


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _today():
    return state.ledger().df["date"].max().date()


def _coverage() -> str:
    info = state.ledger().info
    return f"{info.date_min} to {info.date_max}"


def fallback_plan() -> QueryPlan:
    """When understanding fails, still say something true about this month."""
    from backend.analysis.query import resolve_period

    return QueryPlan(metric=Metric.summary,
                     period=resolve_period(PeriodKind.this_month, _today()),
                     source=PlanSource.pattern)


def decide(text: str) -> tuple[Intent, QueryPlan | None]:
    """Hardcoded advice refusal first (§1.3), then the model decides everything else."""
    if safety.is_advice(text):
        return Intent.advice_refused, None
    # Asking the same thing twice should not cost another planning call. Only cached when
    # there is no history, since a follow-up means the same words can mean something else.
    cache_key = text.strip().lower()
    if not state.state.history and (hit := state.state.decisions.get(cache_key)):
        return hit
    intent, plan = planner.decide(text, state.vocabulary(), state.state.history,
                                  _today(), _coverage())
    if not state.state.history and intent != Intent.unknown:
        state.state.decisions[cache_key] = (intent, plan)
    if intent == Intent.unknown:  # model unreachable or unusable: answer generally
        return Intent.lookup, fallback_plan()
    return intent, plan


def compute_lookup(plan: QueryPlan, discreet: bool, understood: str | None) -> state.CachedAnswer:
    hit = state.cached_lookup(plan, discreet)
    if hit and hit.bundle.understood == understood:
        return hit
    digest = state.state.digest
    t0 = time.perf_counter()
    bundle = build_lookup_bundle(state.ledger().df, plan, understood)
    analysis_ms = _ms(t0)
    t1 = time.perf_counter()
    narration = narrate(bundle, discreet)
    answer = state.CachedAnswer(bundle, narration.text, narration.source, narration.guard,
                                analysis_ms, _ms(t1))
    state.store_lookup(plan, discreet, answer, digest)
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


def _suggestions() -> list[str]:
    vocab = state.vocabulary()
    category = next((c for c in ("groceries", "dining", "subscriptions") if c in
                     vocab.categories), vocab.categories[0] if vocab.categories else "groceries")
    return ["what's unusual this month", f"how much you spent on {category}"]


def answer(text: str, channel: Channel = Channel.text, discreet: bool = False) -> Turn:
    start = time.perf_counter()
    bundle = None
    audio_url = None
    guard = GuardResult(passed=True, attempts=0)
    analysis_ms = narration_ms = 0

    intent, plan = decide(text)

    if intent == Intent.replay:
        narration = state.state.last_narration or refusals.NOTHING_TO_REPEAT
        source = NarrationSource.replay
    elif intent == Intent.unsupported:
        narration, source = refusals.unsupported(_suggestions()), NarrationSource.refusal
    elif intent in FIXED_ANSWERS:
        narration, source = FIXED_ANSWERS[intent]
    elif get_settings().demo_mode and (demo := _demo_turn(intent)) is not None:
        narration, source, bundle, guard, audio_url = (
            demo.narration, demo.narration_source, demo.fact_bundle, demo.guard, demo.audio_url
        )
    else:
        plan = plan or fallback_plan()
        understood = understood_phrase(plan)
        result = compute_lookup(plan, discreet, understood)
        narration, source, bundle, guard = (result.narration, result.source, result.bundle,
                                            result.guard)
        analysis_ms, narration_ms = result.analysis_ms, result.narration_ms
        state.state.last_plan = plan

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
    state.remember(text, plan)
    transcript.record(turn)
    events.publish_turn(turn)
    return turn


def warm_async() -> None:
    """Load the ledger and build the overview ahead of the first question."""
    def run() -> None:
        try:
            state.vocabulary()
            build_lookup_bundle(state.ledger().df, fallback_plan())
        except Exception:
            log.exception("warm-up failed")

    settings = get_settings()
    if settings.precompute and not settings.demo_mode:
        threading.Thread(target=run, name="warmup", daemon=True).start()
