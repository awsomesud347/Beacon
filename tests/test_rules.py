"""Acceptance test (build-spec §4): the engine finds all five planted anomalies and nothing else."""

import pandas as pd
import pytest

from backend.analysis import rules
from backend.analysis.loader import load_path
from backend.contract import AnomalyType
from data.generate import FIXTURES, PLANTED


@pytest.fixture(scope="module", params=["demo_persona.csv", "demo_persona_seed7.csv"])
def findings(request):
    return rules.detect_all(load_path(FIXTURES / request.param).df)


def one(findings, anomaly_type):
    matches = [f.anomaly for f in findings if f.anomaly.type == anomaly_type]
    assert len(matches) == 1, f"expected one {anomaly_type}, got {matches}"
    return matches[0]


def test_new_recurring(findings):
    a = one(findings, AnomalyType.new_recurring)
    assert sorted(a.merchants) == sorted(PLANTED["new_recurring"]["merchants"])
    assert a.count == 3
    assert a.total == 47.00
    assert a.category == "subscriptions"


def test_duplicate_charge(findings):
    a = one(findings, AnomalyType.duplicate_charge)
    assert a.merchants == [PLANTED["duplicate_charge"]["merchant"]]
    assert a.amount == PLANTED["duplicate_charge"]["amount"]
    assert a.count == 2


def test_amount_drift(findings):
    a = one(findings, AnomalyType.amount_drift)
    assert a.merchants == [PLANTED["amount_drift"]["merchant"]]
    assert a.previous_amount == PLANTED["amount_drift"]["previous_amount"]
    assert a.amount == PLANTED["amount_drift"]["amount"]
    assert a.change_pct == 16.1


def test_missing_recurring(findings):
    a = one(findings, AnomalyType.missing_recurring)
    assert a.merchants == [PLANTED["missing_recurring"]["merchant"]]
    assert a.amount == PLANTED["missing_recurring"]["amount"]


def test_category_outlier(findings):
    a = one(findings, AnomalyType.category_outlier)
    assert a.category == PLANTED["category_outlier"]["category"]
    assert a.amount > a.typical_amount


def test_no_false_positives(findings):
    assert sorted(f.anomaly.type for f in findings) == sorted(PLANTED)


def test_hero_anomaly_ranks_first(findings):
    assert findings[0].anomaly.type == AnomalyType.new_recurring


def test_large_transaction_detected_when_present():
    ledger = load_path(FIXTURES / "demo_persona.csv")
    df = ledger.df.copy()
    big = df.iloc[[-1]].copy()
    big["merchant"], big["display"], big["category"], big["amount"] = (
        "BEST BUY 00412", "Best Buy", "shopping", -2400.00
    )
    found = rules.detect_all(pd.concat([df, big], ignore_index=True))
    a = one(found, AnomalyType.large_transaction)
    assert a.amount == 2400.00
    assert a.merchants == ["Best Buy"]
