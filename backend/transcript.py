"""Append-only record of every question and answer, for reviewing a rehearsal or a demo.

Not part of the product: nothing reads it back. It exists so "what did the judges actually
ask, and what did it say?" has an answer afterwards.
"""

import json
import logging
from pathlib import Path

from backend.contract import Turn

log = logging.getLogger("beacon.transcript")
LOG_PATH = Path("logs/turns.jsonl")


def record(turn: Turn) -> None:
    plan = turn.fact_bundle.plan if turn.fact_bundle else None
    entry = {
        "at": turn.created_at.isoformat(timespec="seconds"),
        "channel": turn.channel.value,
        "question": turn.query_text,
        "intent": turn.intent.value,
        "answer": turn.narration,
        "source": turn.narration_source.value,
        "plan": (f"{plan.metric.value} / {plan.subject.value or 'everything'} / "
                 f"{plan.period.label} / via {plan.source.value}") if plan else None,
        "guard_passed": turn.guard.passed,
        "guard_rejected": turn.guard.rejected_tokens,
        "ms": turn.latency_ms.total,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        log.exception("could not write the turn log")
