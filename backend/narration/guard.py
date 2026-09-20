"""Numeric fidelity guard (build-spec §5.3, F8).

Every number in the narration must appear in the fact bundle. Formatting variance is
allowed ($47 / 47.00 / forty-seven, rounding to a whole number); nothing else is.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.contract import FactBundle

log = logging.getLogger("beacon.guard")
LOG_PATH = Path("logs/guard.jsonl")

_NUMERIC = re.compile(r"(?<![\w.])[-−]?\$?\d[\d,]*(?:\.\d+)?%?")
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_NUMBER_WORDS = set(_UNITS) | set(_TENS) | set(_SCALES)
# Spelled-out "one" is almost always "one thing" / "one of", not a figure.
_SAFE_WORD_VALUES = {1.0}


@dataclass
class GuardCheck:
    passed: bool
    rejected: list[str] = field(default_factory=list)


@dataclass
class Allowed:
    """Bundle numbers by unit, so "3%" can't be justified by a count of 3."""

    money: set[float] = field(default_factory=set)
    pct: set[float] = field(default_factory=set)
    other: set[float] = field(default_factory=set)

    @property
    def any(self) -> set[float]:
        return self.money | self.pct | self.other


def _collect(value, out: Allowed, key: str = "") -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        (out.pct if key.endswith("pct") else out.money).add(abs(value))
    elif isinstance(value, int):
        (out.pct if key.endswith("pct") else out.other).add(abs(float(value)))
    elif isinstance(value, str):
        out.other.update(float(n) for n in re.findall(r"\d+(?:\.\d+)?", value))
    elif isinstance(value, dict):
        for k, v in value.items():
            _collect(v, out, k)
    elif isinstance(value, list):
        out.other.add(float(len(value)))
        for v in value:
            _collect(v, out, key)


def allowed_numbers(bundle: FactBundle) -> Allowed:
    out = Allowed()
    _collect(json.loads(bundle.model_dump_json()), out)
    return out


def _words_to_number(words: list[str]) -> float:
    total, current = 0, 0
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * _SCALES[w]
            current = 0
    return float(total + current)


def extract(text: str) -> list[tuple[str, float, bool]]:
    """Return (token, value, spelled) for every number in the text."""
    found = []
    for m in _NUMERIC.finditer(text):
        token = m.group(0)
        raw = re.sub(r"[$,%−-]", "", token)
        if raw:
            found.append((token, abs(float(raw)), False))
    words = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    run: list[str] = []
    for w in [*words, ""]:
        if w in _NUMBER_WORDS or (w == "and" and run):
            run.append(w)
            continue
        while run and run[-1] == "and":
            run.pop()
        if run:
            found.append((" ".join(run), _words_to_number(run), True))
        run = []
    return found


def _matches(value: float, allowed: set[float]) -> bool:
    for a in allowed:
        if abs(value - a) < 0.005:
            return True
        if value.is_integer() and value == round(a):
            return True
    return False


def allowed_names(bundle: FactBundle) -> set[str]:
    """Every category or merchant the narration is entitled to mention."""
    names: set[str] = set()

    def collect(value) -> None:
        if isinstance(value, str):
            names.add(value.lower())
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"name", "value", "category", "merchant", "merchants",
                           "subject_label", "period", "period_label", "prior_label",
                           "understood"}:
                    collect(item)
                elif isinstance(item, dict | list):
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(json.loads(bundle.model_dump_json()))
    return names


def check_names(text: str, bundle: FactBundle, vocabulary: set[str]) -> list[str]:
    """Catch a mislabelled answer: a real category or merchant that this bundle is not
    about. The numeric guard cannot see this — the figures may be perfectly true while
    the thing they are attached to is wrong."""
    allowed = allowed_names(bundle)
    lowered = text.lower()
    return sorted({
        name for name in vocabulary
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered)
        and not any(name.lower() in permitted for permitted in allowed)
    })


def _candidates(token: str, allowed: Allowed) -> set[float]:
    if token.endswith("%"):
        return allowed.pct
    if "$" in token:
        return allowed.money
    return allowed.any


def check(text: str, bundle: FactBundle, vocabulary: set[str] | None = None) -> GuardCheck:
    allowed = allowed_numbers(bundle)
    rejected = [
        token for token, value, spelled in extract(text)
        if not _matches(value, _candidates(token, allowed))
        and not (spelled and value in _SAFE_WORD_VALUES)
    ]
    if vocabulary:
        rejected += check_names(text, bundle, vocabulary)
    return GuardCheck(passed=not rejected, rejected=rejected)


def record(intent: str, attempt: int, result: GuardCheck, text: str,
           question: str | None = None) -> None:
    entry = {"ts": time.time(), "intent": intent, "question": question, "attempt": attempt,
             "passed": result.passed, "rejected": result.rejected, "text": text}
    if not result.passed:
        log.warning("guard tripped: %s", entry)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        log.exception("could not write guard log")
