"""answer(text) -> Turn. The one code path behind both POST /api/query and the voice proxy,
so typed and spoken answers can never disagree.

Routing order, cheapest and most certain first:
  1. deterministic patterns  — hero questions, refusals, identity, scoped lookups (no model)
  2. follow-up merge         — "what about last month?" against the previous plan
  3. model parser            — anything else, validated back against the real data
  4. honest refusal          — understood but unanswerable, or not understood at all
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend import events, state
from backend import intent as routing
from backend.analysis.query import understood_phrase
from backend.analysis.summarize import build_bundle, build_lookup_bundle
from backend.config import get_settings
from backend.contract import (
    Channel,
    GuardResult,
    Intent,
    Latency,
    NarrationSource,
    PlanSource,
    QueryPlan,
    Turn,
)
from backend.narration import parser, refusals
from backend.narration.client import narrate

log = logging.getLogger("beacon.service")
DEMO_CACHE = Path("data/demo_cache")
PRECOMPUTE = (Intent.anomalies, Intent.month_summary)
FIXED_ANSWERS = {
    Intent.advice_refused: (refusals.ADVICE, NarrationSource.refusal),
    Intent.identity: (refusals.IDENTITY, NarrationSource.refusal),
    Intent.help: (refusals.HELP, NarrationSource.template),
    Intent.unknown: (refusals.UNKNOWN, NarrationSource.template),
}


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def compute(intent: Intent, discreet: bool) -> state.CachedAnswer:
    """Analysis + narration for one of the standing questions, cached per dataset."""
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
    """Capability examples built from the data actually loaded."""
    vocab = state.vocabulary()
    category = vocab.categories[0] if vocab.categories else "groceries"
    for preferred in ("groceries", "dining", "subscriptions"):
        if preferred in vocab.categories:
            category = preferred
            break
    return ["what's unusual this month", f"how much you spent on {category}"]


def resolve(text: str, use_parser: bool = True) -> routing.Routed:
    """Pattern -> follow-up -> parser. Returns what to answer and whether to read it back."""
    vocab = state.vocabulary()
    today = state.ledger().df["date"].max().date()
    previous = state.state.last_plan

    # Follow-ups are checked first: "and coffee?" must inherit the previous period rather
    # than be read as a fresh question about this month.
    if previous and routing.is_followup(text):
        if merged := routing.merge_followup(text, previous, vocab, today):
            return routing.Routed(Intent.lookup, plan=merged, inferred=True)

    routed = routing.route(text, vocab, today)
    if routed.intent != Intent.unknown:
        return routed

    if use_parser and get_settings().parser_enabled:
        if plan := parser.parse(text, vocab, previous, today):
            return routing.Routed(Intent.lookup, plan=plan, inferred=True)
        return routing.Routed(Intent.unsupported)
    return routed


def answer(text: str, channel: Channel = Channel.text, discreet: bool = False) -> Turn:
    start = time.perf_counter()
    bundle = None
    audio_url = None
    guard = GuardResult(passed=True, attempts=0)
    analysis_ms = narration_ms = 0

    routed = resolve(text)
    intent = routed.intent

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
    elif intent == Intent.lookup and routed.plan is not None:
        plan = routed.plan
        # Read the understanding back when anything was inferred, carried over or parsed.
        understood = (understood_phrase(plan)
                      if routed.inferred or plan.source != PlanSource.pattern else None)
        result = compute_lookup(plan, discreet, understood)
        narration, source, bundle, guard = (result.narration, result.source, result.bundle,
                                            result.guard)
        analysis_ms, narration_ms = result.analysis_ms, result.narration_ms
        state.state.last_plan = plan
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
