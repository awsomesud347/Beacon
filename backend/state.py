"""Process-wide session state: the loaded ledger and cached answers. Single-user demo; no
persistence beyond the process (build-spec §1.3)."""

import hashlib
import threading
from dataclasses import dataclass, field

from backend.analysis.loader import Ledger, load_csv, load_path
from backend.config import get_settings
from backend.contract import DatasetInfo, FactBundle, GuardResult, Intent, NarrationSource


@dataclass
class CachedAnswer:
    bundle: FactBundle
    narration: str
    source: NarrationSource
    guard: GuardResult
    analysis_ms: int
    narration_ms: int


@dataclass
class State:
    ledger: Ledger | None = None
    digest: str = ""
    answers: dict[tuple[Intent, bool], CachedAnswer] = field(default_factory=dict)
    last_narration: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


state = State()


def _install(ledger: Ledger, raw: bytes) -> DatasetInfo:
    with state.lock:
        state.ledger = ledger
        state.digest = hashlib.sha256(raw).hexdigest()[:16]
        state.answers.clear()
    return ledger.info


def load_default() -> DatasetInfo:
    path = get_settings().dataset_path
    ledger = load_path(path, source="fixture")
    with open(path, "rb") as f:
        return _install(ledger, f.read())


def load_upload(raw: bytes, name: str) -> DatasetInfo:
    return _install(load_csv(raw, name, source="upload"), raw)


def ledger() -> Ledger:
    if state.ledger is None:
        load_default()
    assert state.ledger is not None
    return state.ledger


def dataset_info() -> DatasetInfo | None:
    return state.ledger.info if state.ledger else None


def cached(intent: Intent, discreet: bool) -> CachedAnswer | None:
    return state.answers.get((intent, discreet))


def store(intent: Intent, discreet: bool, answer: CachedAnswer, digest: str) -> None:
    with state.lock:
        if digest == state.digest:  # dataset may have changed mid-computation
            state.answers[(intent, discreet)] = answer
