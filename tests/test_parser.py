"""The parser's safety net, without calling a model.

The model may only choose filters, and only ones that exist in the data. Anything else has
to become None so the caller answers honestly instead of guessing.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.analysis.loader import load_path
from backend.analysis.vocab import build as build_vocab
from backend.contract import Metric, PeriodKind, PlanSource, Subject, SubjectKind
from backend.narration.parser import RawPlan, _to_plan
from data.generate import FIXTURES

TODAY = date(2026, 9, 30)


@pytest.fixture(scope="module")
def vocab():
    return build_vocab(load_path(FIXTURES / "demo_persona.csv").df, "test")


def raw(**kwargs) -> RawPlan:
    return RawPlan(**{"metric": "total_out", **kwargs})


def test_valid_plan_is_accepted(vocab):
    plan = _to_plan(raw(subject_kind="category", subject="groceries",
                        period_kind="named_month", period_value="July"), vocab, TODAY)
    assert plan.subject.value == "groceries"
    assert plan.period.label == "July 2026"
    assert plan.source == PlanSource.model


def test_subject_casing_is_repaired(vocab):
    plan = _to_plan(raw(subject_kind="merchant", subject="kROGER"), vocab, TODAY)
    assert plan.subject.value == "Kroger"


def test_invented_subject_is_rejected(vocab):
    assert _to_plan(raw(subject_kind="category", subject="crypto"), vocab, TODAY) is None
    assert _to_plan(raw(subject_kind="merchant", subject="Acme Casino"), vocab, TODAY) is None


def test_subject_kind_mismatch_is_repaired_not_guessed(vocab):
    # The model called a category a merchant; the value is real, so it is corrected.
    plan = _to_plan(raw(subject_kind="merchant", subject="groceries"), vocab, TODAY)
    assert plan.subject.kind == SubjectKind.category
    assert plan.subject.value == "groceries"


@pytest.mark.parametrize(
    "payload",
    [
        '{"metric": "unsupported"}',
        '{"metric": "transfer_money"}',
        '{"metric": "total_out", "period_kind": "since_forever"}',
        '{"metric": "total_out", "subject_kind": "account"}',
        '{"metric": 5}',
        "{}",
        "not json at all",
    ],
)
def test_unusable_model_output_never_becomes_a_plan(payload):
    with pytest.raises((ValidationError, ValueError)):
        RawPlan.model_validate_json(payload)


def test_days_are_read_from_period_value(vocab):
    plan = _to_plan(raw(period_kind="last_n_days", period_value="14"), vocab, TODAY)
    assert plan.period.kind == PeriodKind.last_n_days
    assert plan.period.label == "the last 14 days"
    assert (plan.period.end - plan.period.start).days == 13


def test_garbage_period_value_falls_back_to_this_month(vocab):
    plan = _to_plan(raw(period_kind="named_month", period_value="smorptember"), vocab, TODAY)
    assert plan.period.label == "September 2026"


def test_no_subject_means_everything(vocab):
    plan = _to_plan(raw(metric="top_categories"), vocab, TODAY)
    assert plan.subject == Subject()
    assert plan.metric == Metric.top_categories


def test_vocabulary_rejects_what_is_not_in_the_ledger(vocab):
    assert vocab.resolve("pets") is None
    assert vocab.resolve("crypto") is None
    assert vocab.resolve("eating out").value == "dining"
    assert vocab.resolve("gas").value == "transport"
    assert vocab.resolve("netflix").value == "Netflix"
