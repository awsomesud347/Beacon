import pytest

from backend.contract import Intent
from backend.intent import route


@pytest.mark.parametrize(
    "text,intent",
    [
        ("What's unusual?", Intent.anomalies),
        ("Is anything weird this month?", Intent.anomalies),
        ("Anything stand out?", Intent.anomalies),
        ("How am I doing this month?", Intent.month_summary),
        ("How's my month going?", Intent.month_summary),
        ("Am I okay?", Intent.month_summary),
        ("Where did my money go?", Intent.where_money_went),
        ("Give me a breakdown", Intent.where_money_went),
        ("What did I spend the most on?", Intent.where_money_went),
        ("How does this compare to last month?", Intent.compare_last_month),
        ("How am I doing compared to last month?", Intent.compare_last_month),
        ("Should I cancel Netflix?", Intent.advice_refused),
        ("Can I afford a new TV?", Intent.advice_refused),
        ("Will I have enough next month?", Intent.advice_refused),
        ("Should I invest?", Intent.advice_refused),
        ("Repeat that", Intent.replay),
        ("Say that again", Intent.replay),
        ("What can you do?", Intent.help),
        ("What's the weather?", Intent.unknown),
    ],
)
def test_route(text, intent):
    assert route(text) == intent
