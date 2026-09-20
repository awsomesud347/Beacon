"""The execution engine, checked against ground truth computed a different way."""

from datetime import date

import pandas as pd
import pytest

from backend.analysis import query
from backend.analysis.loader import load_path
from backend.analysis.vocab import build as build_vocab
from backend.contract import Metric, Period, PeriodKind, QueryPlan, Subject, SubjectKind
from data.generate import FIXTURES

TODAY = date(2026, 9, 30)  # the fixture's last transaction


@pytest.fixture(scope="module")
def df():
    return load_path(FIXTURES / "demo_persona.csv").df


@pytest.fixture(scope="module")
def vocab(df):
    return build_vocab(df, "test")


def plan(metric, kind=PeriodKind.this_month, subject=None, value=None, limit=None):
    return QueryPlan(
        metric=metric,
        subject=subject or (Subject(kind=SubjectKind.category, value=value) if value
                            else Subject()),
        period=query.resolve_period(kind, TODAY),
        limit=limit,
    )


def september(df):
    return df[df["date"].dt.to_period("M") == pd.Period("2026-09")]


def test_period_resolution_uses_the_ledger_not_the_clock(df):
    assert query.as_of(df).date() == TODAY
    assert query.resolve_period(PeriodKind.this_month, TODAY).label == "September 2026"
    assert query.resolve_period(PeriodKind.last_month, TODAY).label == "August 2026"
    assert query.resolve_period(PeriodKind.named_month, TODAY, "July").label == "July 2026"
    # A month later than the ledger's month means last year, not the future.
    assert query.resolve_period(PeriodKind.named_month, TODAY, "December").label == "December 2025"
    week = query.resolve_period(PeriodKind.this_week, TODAY)
    assert week.start == date(2026, 9, 28) and week.end == TODAY
    assert query.resolve_period(PeriodKind.last_n_days, TODAY, days=30).start == date(2026, 9, 1)


def test_total_out_matches_raw_sum(df):
    result = query.execute(plan(Metric.total_out), df)
    sept = september(df)
    expected = round(-sept.loc[sept["amount"] < 0, "amount"].sum(), 2)
    assert result.total == pytest.approx(expected)
    assert result.period_label == "September 2026"
    assert result.subject_label == "everything"


def test_category_spend_matches_raw_sum(df):
    result = query.execute(plan(Metric.total_out, value="groceries"), df)
    sept = september(df)
    expected = round(-sept.loc[(sept["category"] == "groceries") & (sept["amount"] < 0),
                               "amount"].sum(), 2)
    assert result.total == pytest.approx(expected)
    assert result.subject_label == "groceries"
    assert result.prior_total and result.delta_pct is not None


def test_merchant_spend_and_count(df, vocab):
    subject = vocab.resolve("kroger")
    assert subject and subject.kind == SubjectKind.merchant
    result = query.execute(plan(Metric.count, subject=subject), df)
    sept = september(df)
    rows = sept[(sept["display"] == subject.value) & (sept["amount"] < 0)]
    assert result.count == len(rows)
    assert result.total == pytest.approx(round(-rows["amount"].sum(), 2))


def test_average(df):
    result = query.execute(plan(Metric.average, value="coffee"), df)
    assert result.average == pytest.approx(round(result.total / result.count, 2))


def test_largest_and_smallest_ignore_rent(df):
    """"Biggest purchase" means a purchase: rent is a payment and would win every month."""
    sept = september(df)
    out = sept[(sept["amount"] < 0) & (sept["category"] != "rent")]
    biggest = out.loc[out["amount"].idxmin()]
    result = query.execute(plan(Metric.largest), df)
    assert result.largest.amount == pytest.approx(round(abs(biggest["amount"]), 2))
    assert result.largest.merchant == biggest["display"]
    assert result.largest.merchant != "Oakwood Apartments"

    smallest = out.loc[out["amount"].idxmax()]
    low = query.execute(plan(Metric.smallest), df)
    assert low.largest.amount == pytest.approx(round(abs(smallest["amount"]), 2))


def test_largest_keeps_rent_when_rent_is_the_subject(df):
    p = QueryPlan(metric=Metric.largest,
                  subject=Subject(kind=SubjectKind.category, value="rent"),
                  period=query.resolve_period(PeriodKind.this_month, TODAY))
    assert query.execute(p, df).largest.merchant == "Oakwood Apartments"


def test_income_and_net(df):
    sept = september(df)
    income = round(sept.loc[sept["amount"] > 0, "amount"].sum(), 2)
    spent = round(-sept.loc[sept["amount"] < 0, "amount"].sum(), 2)

    assert query.execute(plan(Metric.total_in), df).total == pytest.approx(income)
    net = query.execute(plan(Metric.net), df)
    assert net.total == pytest.approx(round(income - spent, 2))
    assert [i.name for i in net.items] == ["money in", "money out"]


def test_top_categories_and_merchants(df):
    top = query.execute(plan(Metric.top_categories, limit=3), df)
    assert [i.name for i in top.items] == ["rent", "groceries", "dining"]
    assert top.items[0].amount >= top.items[1].amount >= top.items[2].amount

    merchants = query.execute(plan(Metric.top_merchants, limit=5), df)
    assert len(merchants.items) == 5
    assert merchants.items[0].name == "Oakwood Apartments"  # rent is the biggest single payee


def test_list_recurring_finds_the_subscriptions(df):
    result = query.execute(plan(Metric.list_recurring), df)
    names = [i.name for i in result.items]
    assert "Netflix" in names and "Spotify" in names
    assert result.count == len(names) or result.count >= len(names)
    assert not result.empty


def test_named_month_scopes_to_that_month(df):
    july = query.execute(plan(Metric.total_out, kind=PeriodKind.named_month), df)
    assert july.period_label == "September 2026"  # no value given -> falls back to this month

    p = QueryPlan(metric=Metric.total_out, period=query.resolve_period(
        PeriodKind.named_month, TODAY, "July"))
    result = query.execute(p, df)
    month = df[df["date"].dt.to_period("M") == pd.Period("2026-07")]
    assert result.total == pytest.approx(round(-month.loc[month["amount"] < 0, "amount"].sum(), 2))


def test_empty_subject_is_zero_not_an_error(df):
    p = QueryPlan(
        metric=Metric.total_out,
        subject=Subject(kind=SubjectKind.category, value="pets"),
        period=query.resolve_period(PeriodKind.this_month, TODAY),
    )
    result = query.execute(p, df)
    assert result.empty is True
    assert result.total == 0 and result.count == 0


def test_period_boundaries_are_inclusive(df):
    p = QueryPlan(metric=Metric.count, period=Period(
        kind=PeriodKind.named_month, label="one day", start=TODAY, end=TODAY))
    result = query.execute(p, df)
    same_day = df[(df["date"].dt.date == TODAY) & (df["amount"] < 0)]
    assert result.count == len(same_day)
