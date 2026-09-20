"""Routing: the fast path must be right or silent — never confidently wrong."""

from datetime import date

import pytest

from backend.analysis.loader import load_path
from backend.analysis.vocab import build as build_vocab
from backend.contract import Intent, Metric, PeriodKind, PlanSource, SubjectKind
from backend.intent import is_followup, merge_followup, route
from data.generate import FIXTURES

TODAY = date(2026, 9, 30)


@pytest.fixture(scope="module")
def vocab():
    return build_vocab(load_path(FIXTURES / "demo_persona.csv").df, "test")


def r(text, vocab):
    return route(text, vocab, TODAY)


@pytest.mark.parametrize(
    "text,intent",
    [
        ("What's unusual?", Intent.anomalies),
        ("Is anything weird this month?", Intent.anomalies),
        ("How am I doing this month?", Intent.month_summary),
        ("Am I okay?", Intent.month_summary),
        ("Where did my money go?", Intent.where_money_went),
        ("How does this compare to last month?", Intent.compare_last_month),
        ("Should I cancel Netflix?", Intent.advice_refused),
        ("Can I afford a new TV?", Intent.advice_refused),
        ("Repeat that", Intent.replay),
        ("What can you do?", Intent.help),
        ("Who are you?", Intent.identity),
        ("Is this real data?", Intent.identity),
        # Understood well enough to know we can't answer it: say so, don't guess.
        ("What's the weather?", Intent.unsupported),
        ("What's my bank balance?", Intent.unsupported),
        ("Transfer $50 to my sister", Intent.unsupported),
        ("Do you think I spend too much?", Intent.advice_refused),
        ("What will I spend next month?", Intent.advice_refused),
        ("Anything I should know about this month?", Intent.anomalies),
    ],
)
def test_fixed_intents(text, intent, vocab):
    assert r(text, vocab).intent == intent


@pytest.mark.parametrize(
    "text,metric,kind,value",
    [
        ("how much did I spend on groceries?", Metric.total_out, SubjectKind.category,
         "groceries"),
        ("what did I spend at Kroger?", Metric.total_out, SubjectKind.merchant, "Kroger"),
        ("how much on dining out?", Metric.total_out, SubjectKind.category, "dining"),
        ("how much do I spend on gas?", Metric.total_out, SubjectKind.category, "transport"),
        ("how many times did I eat out?", Metric.count, SubjectKind.category, "dining"),
        ("what was my biggest purchase?", Metric.largest, SubjectKind.all, None),
        # "subscriptions" names a real category, so the list is scoped to it; a broader
        # "what are my recurring charges?" stays unscoped (below).
        ("what subscriptions do I have?", Metric.list_recurring, SubjectKind.category,
         "subscriptions"),
        ("what are my recurring charges?", Metric.list_recurring, SubjectKind.all, None),
        ("where do I shop the most?", Metric.top_merchants, SubjectKind.all, None),
        ("how much did I make this month?", Metric.total_in, SubjectKind.all, None),
        ("am I saving money?", Metric.net, SubjectKind.all, None),
        ("is my dining spending going up?", Metric.trend, SubjectKind.category, "dining"),
        ("what's my average grocery trip?", Metric.average, SubjectKind.category, "groceries"),
    ],
)
def test_scoped_questions_become_plans(text, metric, kind, value, vocab):
    routed = r(text, vocab)
    assert routed.intent == Intent.lookup, text
    assert routed.plan.metric == metric
    assert routed.plan.subject.kind == kind
    assert routed.plan.subject.value == value


@pytest.mark.parametrize(
    "text,kind,label",
    [
        ("how much did I spend in July?", PeriodKind.named_month, "July 2026"),
        ("how much last month?", PeriodKind.last_month, "August 2026"),
        ("what did I spend this week?", PeriodKind.this_week, "this week"),
        ("how much in the last 30 days?", PeriodKind.last_n_days, "the last 30 days"),
        ("how much this year?", PeriodKind.this_year, "2026"),
    ],
)
def test_time_ranges(text, kind, label, vocab):
    plan = r(text, vocab).plan
    assert plan is not None, text
    assert plan.period.kind == kind
    assert plan.period.label == label


def test_unnamed_period_is_flagged_for_read_back(vocab):
    assert r("how much on groceries?", vocab).inferred is True
    assert r("how much on groceries in July?", vocab).inferred is False


class TestMeasuredMisroutes:
    """The three questions that today's router answered as something else entirely."""

    def test_merchant_question_is_not_a_month_summary(self, vocab):
        routed = r("did Netflix charge me this month?", vocab)
        assert routed.intent == Intent.lookup
        assert routed.plan.subject.value == "Netflix"

    def test_factual_spend_question_is_not_advice(self, vocab):
        assert r("how much do I spend on gas?", vocab).intent == Intent.lookup

    def test_in_versus_out_is_net_not_compare(self, vocab):
        routed = r("what came in versus what went out?", vocab)
        assert routed.intent == Intent.lookup
        assert routed.plan.metric == Metric.net


class TestFollowUps:
    def test_recognised(self):
        assert is_followup("what about last month?")
        assert is_followup("and groceries?")
        assert not is_followup("how much did I spend?")

    def test_period_carries_the_subject(self, vocab):
        first = r("how much on groceries?", vocab).plan
        merged = merge_followup("what about last month?", first, vocab, TODAY)
        assert merged.subject.value == "groceries"
        assert merged.period.kind == PeriodKind.last_month
        assert merged.source == PlanSource.followup

    def test_subject_carries_the_period(self, vocab):
        first = r("how much on groceries in July?", vocab).plan
        merged = merge_followup("and coffee?", first, vocab, TODAY)
        assert merged.subject.value == "coffee"
        assert merged.period.label == "July 2026"

    def test_empty_followup_is_rejected(self, vocab):
        first = r("how much on groceries?", vocab).plan
        assert merge_followup("and, um", first, vocab, TODAY) is None
