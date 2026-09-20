from datetime import date

import pytest

from backend.analysis.loader import load_path
from backend.analysis.query import resolve_period
from backend.analysis.summarize import build_bundle, build_lookup_bundle
from backend.analysis.vocab import build as build_vocab
from backend.contract import (
    FactBundle,
    Intent,
    Metric,
    PeriodKind,
    QueryPlan,
    Subject,
    SubjectKind,
)
from backend.contract_export import CONTRACT_DIR
from backend.narration import guard, templates
from backend.narration.client import tidy_numbers
from data.generate import FIXTURES

BUNDLE = FactBundle.model_validate_json(
    (CONTRACT_DIR / "examples" / "fact_bundle_anomalies.json").read_text()
)


@pytest.mark.parametrize(
    "text",
    [
        "Your spending is normal except for one thing: three new subscriptions totaling $47.",
        "You have 3 new subscriptions totaling $47.00.",
        "Three new subscriptions came to forty-seven dollars.",
        "Corner Bistro charged you $38.50 twice.",
        "StreamFlix went from $15.49 to $17.99, up 16.1%.",
        "You've spent $2,914.22 in September 2026, up 1.5% from last month.",
        "StreamFlix went up about 16%.",
        "Your spending looks normal.",
    ],
)
def test_accepts_faithful_narration(text):
    result = guard.check(text, BUNDLE)
    assert result.passed, result.rejected


@pytest.mark.parametrize(
    "text,bad",
    [
        ("You spent $4,200 on groceries.", "$4,200"),
        ("Three subscriptions totaling $48.", "$48"),
        ("Your subscriptions cost $564 a year.", "$564"),  # 47 x 12: computed, not given
        ("Spending is up 3% from last month.", "3%"),
        ("You paid twelve dollars more for StreamFlix.", "twelve"),
        ("Corner Bistro double-charged you $77.50.", "$77.50"),
    ],
)
def test_rejects_invented_figures(text, bad):
    result = guard.check(text, BUNDLE)
    assert not result.passed
    assert bad in result.rejected


@pytest.mark.parametrize("discreet", [False, True])
@pytest.mark.parametrize("intent", [Intent.anomalies, Intent.month_summary,
                                    Intent.where_money_went, Intent.compare_last_month])
def test_templates_always_pass_guard(intent, discreet):
    for fixture in ("demo_persona.csv", "demo_persona_seed7.csv"):
        bundle = build_bundle(load_path(FIXTURES / fixture).df, intent)
        text = templates.render(bundle, discreet)
        assert guard.check(text, bundle).passed, text


@pytest.mark.parametrize(
    "raw,tidy",
    [
        ("totaling $47.0 and $1,450.00", "totaling $47 and $1,450"),
        ("charged $38.5 twice", "charged $38.50 twice"),
        ("down 100.0% and up 6.8%", "down 100% and up 6.8%"),
        ("$2,992.94 stays", "$2,992.94 stays"),
    ],
)
def test_tidy_numbers_only_changes_formatting(raw, tidy):
    assert tidy_numbers(raw) == tidy
    assert guard.check(tidy, BUNDLE).passed == guard.check(raw, BUNDLE).passed


class TestNameGuard:
    """A true figure attached to the wrong thing is as harmful as a false one, and the
    numeric guard cannot see it. Regression: the model once copied "For groceries in
    July" out of a prompt example and pinned this month's real total to it."""

    @pytest.fixture(scope="class")
    @classmethod
    def lookup_bundle(cls):
        df = load_path(FIXTURES / "demo_persona.csv").df
        plan = QueryPlan(
            metric=Metric.total_out,
            period=resolve_period(PeriodKind.last_month, date(2026, 9, 30)),
        )
        return build_lookup_bundle(df, plan, "August 2026")

    @pytest.fixture(scope="class")
    @classmethod
    def names(cls):
        vocab = build_vocab(load_path(FIXTURES / "demo_persona.csv").df, "test")
        return {*vocab.categories, *vocab.merchants}

    def test_rejects_a_category_the_answer_is_not_about(self, lookup_bundle, names):
        bad = "For groceries in August 2026, you spent $2,803.34 across 66 purchases."
        result = guard.check(bad, lookup_bundle, names)
        assert not result.passed
        assert "groceries" in result.rejected

    def test_rejects_a_merchant_the_answer_is_not_about(self, lookup_bundle, names):
        result = guard.check("You spent $2,803.34 at Kroger.", lookup_bundle, names)
        assert not result.passed
        assert "Kroger" in result.rejected

    def test_accepts_the_honest_sentence(self, lookup_bundle, names):
        good = "In August 2026, you spent $2,803.34 across 66 purchases."
        assert guard.check(good, lookup_bundle, names).passed

    def test_allows_names_the_bundle_is_about(self, names):
        df = load_path(FIXTURES / "demo_persona.csv").df
        plan = QueryPlan(
            metric=Metric.total_out,
            subject=Subject(kind=SubjectKind.category, value="groceries"),
            period=resolve_period(PeriodKind.last_month, date(2026, 9, 30)),
        )
        bundle = build_lookup_bundle(df, plan, "groceries in August 2026")
        assert guard.check("For groceries in August 2026, you spent $364.36.",
                           bundle, names).passed

    def test_anomaly_merchants_are_allowed(self, names):
        df = load_path(FIXTURES / "demo_persona.csv").df
        bundle = build_bundle(df, Intent.anomalies)
        text = ("Your spending is normal except for three new subscriptions from "
                "Paramount Plus, Audible and CloudVault, totaling $47.")
        assert guard.check(text, bundle, names).passed


def test_discreet_templates_speak_no_money():
    bundle = build_bundle(load_path(FIXTURES / "demo_persona.csv").df, Intent.anomalies)
    assert "$" not in templates.render(bundle, discreet=True)
