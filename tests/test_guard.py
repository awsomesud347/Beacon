import pytest

from backend.analysis.loader import load_path
from backend.analysis.summarize import build_bundle
from backend.contract import FactBundle, Intent
from backend.contract_export import CONTRACT_DIR
from backend.narration import guard, templates
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


def test_discreet_templates_speak_no_money():
    bundle = build_bundle(load_path(FIXTURES / "demo_persona.csv").df, Intent.anomalies)
    assert "$" not in templates.render(bundle, discreet=True)
