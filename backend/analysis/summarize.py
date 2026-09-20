"""Ledger -> FactBundle. Every figure is computed here; the model only phrases them."""

import pandas as pd

from backend.analysis.loader import period_label
from backend.analysis.overview import build as build_overview
from backend.analysis.query import execute
from backend.analysis.rules import (
    Finding,
    MonthView,
    _outflows,
    category_totals,
    detect_all,
    month_view,
)
from backend.contract import (
    CategoryAmount,
    Comparison,
    Context,
    FactBundle,
    Intent,
    Metric,
    MonthSummary,
    QueryPlan,
    Verdict,
)

ANALYSIS_INTENTS = {Intent.anomalies, Intent.month_summary, Intent.where_money_went,
                    Intent.compare_last_month}
TOP_ANOMALIES = 3
TOP_CATEGORIES = 5


def _money(x: float) -> float:
    return round(float(x), 2)


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def _total_out(df: pd.DataFrame) -> float:
    return _money(_outflows(df)["amount"].abs().sum())


def _context(view: MonthView) -> Context:
    current = _total_out(view.current)
    prior = _total_out(view.df[view.df["period"] == view.period - 1])
    return Context(month_total_out=current, prior_month_total_out=prior,
                   delta_pct=_pct(current, prior) or 0.0)


def _verdict(view: MonthView, findings: list[Finding]) -> Verdict:
    if view.current.empty:
        return Verdict.no_data
    trailing = [_total_out(view.df[view.df["period"] == view.period - i]) for i in range(1, 7)]
    series = pd.Series(trailing)
    std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    if std and abs(_total_out(view.current) - float(series.mean())) / std > 2:
        return Verdict.unusual
    return Verdict.normal_with_exception if findings else Verdict.normal


def _category_deltas(view: MonthView) -> list[CategoryAmount]:
    table = category_totals(view.df[view.df["period"].isin([view.period - 1, view.period])])
    table = table.reindex([view.period - 1, view.period], fill_value=0)
    rows = [
        CategoryAmount(name=str(cat), amount=_money(table.loc[view.period, cat]),
                       delta_pct=_pct(table.loc[view.period, cat], table.loc[view.period - 1, cat]))
        for cat in table.columns
    ]
    return sorted(rows, key=lambda c: c.amount, reverse=True)


def _summary(view: MonthView) -> MonthSummary:
    total_in = _money(view.current.loc[view.current["amount"] > 0, "amount"].sum())
    total_out = _total_out(view.current)
    top = [c for c in _category_deltas(view) if c.amount > 0][:TOP_CATEGORIES]
    return MonthSummary(total_in=total_in, total_out=total_out, net=_money(total_in - total_out),
                        top_categories=top)


def _comparison(view: MonthView, context: Context) -> Comparison:
    table = category_totals(view.df[view.df["period"].isin([view.period - 1, view.period])])
    table = table.reindex([view.period - 1, view.period], fill_value=0)
    change = (table.loc[view.period] - table.loc[view.period - 1]).sort_values()

    def entry(cat: str) -> CategoryAmount:
        return CategoryAmount(name=str(cat), amount=_money(table.loc[view.period, cat]),
                              delta_pct=_pct(table.loc[view.period, cat],
                                             table.loc[view.period - 1, cat]))

    return Comparison(
        current_total_out=context.month_total_out,
        prior_total_out=context.prior_month_total_out,
        delta_pct=context.delta_pct,
        biggest_increase=entry(change.index[-1]) if change.iloc[-1] > 0 else None,
        biggest_decrease=entry(change.index[0]) if change.iloc[0] < 0 else None,
    )


def build_lookup_bundle(df: pd.DataFrame, plan: QueryPlan, understood: str | None = None,
                        as_of: pd.Timestamp | None = None) -> FactBundle:
    """Everything the model may use to answer this question: the plan it chose, the figures
    that plan produced, and the standing overview of the ledger."""
    # Anchor the analysis to the period that was asked about: "and last month?" must not
    # describe this month's anomalies under last month's name.
    as_of = as_of or pd.Timestamp(min(plan.period.end, df["date"].max().date()))
    view = month_view(df, as_of)
    findings = detect_all(df, as_of)
    lookup = execute(plan, df)
    bundle = FactBundle(
        query_type=Intent.lookup,
        period=plan.period.label,
        verdict=_verdict(view, findings),
        context=_context(view),
        plan=plan,
        lookup=lookup,
        overview=build_overview(df),
        understood=understood,
    )
    if plan.metric in (Metric.anomalies, Metric.summary):
        bundle.anomalies = [f.anomaly for f in findings[:TOP_ANOMALIES]]
    if plan.metric == Metric.summary:
        bundle.summary = _summary(view)
        bundle.comparison = _comparison(view, bundle.context)
    if lookup.empty and plan.metric not in (Metric.anomalies, Metric.summary):
        bundle.verdict = Verdict.no_data
    return bundle


def build_bundle(df: pd.DataFrame, intent: Intent,
                 as_of: pd.Timestamp | None = None) -> FactBundle:
    if intent not in ANALYSIS_INTENTS:
        raise ValueError(f"{intent} has no fact bundle")
    view = month_view(df, as_of)
    findings = detect_all(df, as_of)
    context = _context(view)
    bundle = FactBundle(
        query_type=intent,
        period=period_label(view.as_of),
        verdict=_verdict(view, findings),
        context=context,
    )
    if intent in (Intent.anomalies, Intent.month_summary):
        bundle.anomalies = [f.anomaly for f in findings[:TOP_ANOMALIES]]
    if intent in (Intent.month_summary, Intent.where_money_went):
        bundle.summary = _summary(view)
    if intent == Intent.compare_last_month:
        bundle.comparison = _comparison(view, context)
    return bundle
