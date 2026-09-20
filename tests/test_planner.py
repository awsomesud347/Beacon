"""The planner's safety net, without calling a model.

Routing is the model's job now, so what matters here is that nothing it returns can become
a confident answer to a question nobody asked.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.analysis.loader import load_path
from backend.analysis.vocab import build as build_vocab
from backend.contract import Metric, PeriodKind, PlanSource, SubjectKind
from backend.narration.client import looks_like_a_sentence
from backend.narration.planner import KINDS, Decision, _to_plan
from data.generate import FIXTURES

TODAY = date(2026, 9, 30)


@pytest.fixture(scope="module")
def vocab():
    return build_vocab(load_path(FIXTURES / "demo_persona.csv").df, "test")


def decision(**kwargs) -> Decision:
    return Decision(**{"kind": "data", "metric": "total_out", **kwargs})


def test_every_kind_maps_to_an_intent():
    assert set(KINDS) == {"data", "advice", "identity", "help", "repeat", "unsupported"}


def test_valid_decision_becomes_a_plan(vocab):
    plan = _to_plan(decision(subject_kind="category", subject="groceries",
                             period_kind="named_month", period_value="July"), vocab, TODAY)
    assert plan.subject.value == "groceries"
    assert plan.period.label == "July 2026"
    assert plan.source == PlanSource.model


def test_misspelled_subject_is_repaired(vocab):
    assert _to_plan(decision(subject_kind="merchant", subject="kROGER"),
                    vocab, TODAY).subject.value == "Kroger"


def test_invented_subject_is_rejected(vocab):
    assert _to_plan(decision(subject_kind="category", subject="crypto"), vocab, TODAY) is None
    assert _to_plan(decision(subject_kind="merchant", subject="Acme Casino"),
                    vocab, TODAY) is None


def test_wrong_subject_kind_is_corrected(vocab):
    plan = _to_plan(decision(subject_kind="merchant", subject="groceries"), vocab, TODAY)
    assert plan.subject.kind == SubjectKind.category


@pytest.mark.parametrize(
    "payload",
    [
        '{"kind": "data", "metric": "transfer_money"}',
        '{"kind": "data", "metric": "total_out", "period_kind": "since_forever"}',
        '{"kind": "data", "metric": "total_out", "subject_kind": "account"}',
        '{"metric": "total_out"}',
        "{}",
        "not json",
    ],
)
def test_unusable_output_cannot_become_a_decision(payload):
    with pytest.raises((ValidationError, ValueError)):
        Decision.model_validate_json(payload)


def test_days_and_months_resolve(vocab):
    days = _to_plan(decision(period_kind="last_n_days", period_value="14"), vocab, TODAY)
    assert days.period.label == "the last 14 days"
    nonsense = _to_plan(decision(period_kind="named_month", period_value="smorptember"),
                        vocab, TODAY)
    assert nonsense.period.label == "September 2026"


def test_unknown_kind_is_treated_as_unsupported():
    assert KINDS.get("something_else") is None


def test_metrics_cover_the_broad_questions():
    assert Metric.summary in Metric and Metric.anomalies in Metric


def test_period_kinds_are_all_resolvable(vocab):
    for kind in PeriodKind:
        plan = _to_plan(decision(period_kind=kind.value), vocab, TODAY)
        assert plan.period.start <= plan.period.end


@pytest.mark.parametrize(
    "text,ok",
    [
        ("You spent $412 across 9 purchases.", True),
        ("13 purchases totaling $314.39", False),  # no verb, no full stop
        ("$47.", False),
        ("", False),
        ("You haven't spent anything on pets in September 2026.", True),
    ],
)
def test_only_speakable_sentences_are_accepted(text, ok):
    assert looks_like_a_sentence(text) is ok
