"""Executing a QueryPlan against the ledger. Pure pandas, zero LLM involvement.

The model may decide *what* to look up (metric, subject, period); every number below is
computed here and checked by the guard before it is spoken.
"""

import calendar
import re
from datetime import date

import pandas as pd

from backend.analysis.rules import _outflows, detect_recurring, month_view
from backend.contract import (
    CategoryAmount,
    Lookup,
    MerchantAmount,
    Metric,
    Period,
    PeriodKind,
    QueryPlan,
    Subject,
    SubjectKind,
)

DEFAULT_LIMIT = 3
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS |= {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def _money(x: float) -> float:
    return round(float(x), 2)


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def as_of(df: pd.DataFrame) -> pd.Timestamp:
    return df["date"].max()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def parse_month(text: str, today: date) -> tuple[int, int] | None:
    """'July', 'july 2025', 'in Dec' -> (year, month). Future months roll back a year."""
    words = re.findall(r"[a-z]+|\d{4}", text.lower())
    month = next((MONTHS[w] for w in words if w in MONTHS), None)
    if not month:
        return None
    year = next((int(w) for w in words if w.isdigit() and len(w) == 4), None)
    if year is None:
        year = today.year if month <= today.month else today.year - 1
    return year, month


def resolve_period(kind: PeriodKind, today: date, value: str | None = None,
                   days: int | None = None) -> Period:
    """Every period is resolved against the ledger's own last date, never the wall clock."""
    match kind:
        case PeriodKind.this_month:
            start, end = month_bounds(today.year, today.month)
            return Period(kind=kind, label=start.strftime("%B %Y"), start=start, end=end)
        case PeriodKind.last_month:
            year, month = ((today.year - 1, 12) if today.month == 1
                           else (today.year, today.month - 1))
            start, end = month_bounds(year, month)
            return Period(kind=kind, label=start.strftime("%B %Y"), start=start, end=end)
        case PeriodKind.named_month:
            found = parse_month(value or "", today)
            if not found:
                return resolve_period(PeriodKind.this_month, today)
            start, end = month_bounds(*found)
            return Period(kind=kind, label=start.strftime("%B %Y"), start=start, end=end)
        case PeriodKind.last_n_days:
            n = days or (int(value) if value and value.isdigit() else 30)
            start = today - pd.Timedelta(days=n - 1)
            return Period(kind=kind, label=f"the last {n} days", start=start, end=today)
        case PeriodKind.this_week:
            start = today - pd.Timedelta(days=today.weekday())
            return Period(kind=kind, label="this week", start=start, end=today)
        case PeriodKind.last_week:
            end = today - pd.Timedelta(days=today.weekday() + 1)
            return Period(kind=kind, label="last week", start=end - pd.Timedelta(days=6), end=end)
        case PeriodKind.this_year:
            return Period(kind=kind, label=str(today.year), start=date(today.year, 1, 1), end=today)
    return Period(kind=PeriodKind.all_time, label="all time", start=date(1970, 1, 1), end=today)


def prior_period(period: Period, today: date) -> Period | None:
    """The comparable window before this one, for 'up 12% from last month'."""
    match period.kind:
        case PeriodKind.this_month | PeriodKind.named_month | PeriodKind.last_month:
            year, month = period.start.year, period.start.month
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
            start, end = month_bounds(year, month)
            return Period(kind=PeriodKind.named_month, label=start.strftime("%B %Y"),
                          start=start, end=end)
        case PeriodKind.last_n_days | PeriodKind.this_week | PeriodKind.last_week:
            span = (period.end - period.start).days + 1
            end = period.start - pd.Timedelta(days=1)
            return Period(kind=period.kind, label=f"the previous {span} days",
                          start=end - pd.Timedelta(days=span - 1), end=end)
    return None


def _window(df: pd.DataFrame, period: Period) -> pd.DataFrame:
    dates = df["date"].dt.date
    return df[(dates >= period.start) & (dates <= period.end)]


def _subject_filter(df: pd.DataFrame, subject: Subject) -> pd.DataFrame:
    if subject.kind == SubjectKind.category and subject.value:
        return df[df["category"].str.lower() == subject.value.lower()]
    if subject.kind == SubjectKind.merchant and subject.value:
        return df[df["display"].str.lower() == subject.value.lower()]
    return df


def subject_label(subject: Subject) -> str:
    return subject.value if subject.value else "everything"


def _spend_total(df: pd.DataFrame) -> float:
    return _money(_outflows(df)["amount"].abs().sum())


def execute(plan: QueryPlan, df: pd.DataFrame) -> Lookup:
    today = as_of(df).date()
    scoped = _subject_filter(_window(df, plan.period), plan.subject)
    out = _outflows(scoped)
    label = subject_label(plan.subject)
    limit = plan.limit or DEFAULT_LIMIT

    lookup = Lookup(
        subject_label=label,
        period_label=plan.period.label,
        total=0.0,
        count=0,
        empty=scoped.empty,
    )

    match plan.metric:
        case Metric.total_in:
            income = scoped[scoped["amount"] > 0]["amount"]
            lookup.total = _money(income.sum())
            lookup.count = int(len(income))
        case Metric.net:
            income = _money(scoped.loc[scoped["amount"] > 0, "amount"].sum())
            spent = _spend_total(scoped)
            lookup.total = _money(income - spent)
            lookup.count = int(len(scoped))
            lookup.items = [
                CategoryAmount(name="money in", amount=income),
                CategoryAmount(name="money out", amount=spent),
            ]
        case Metric.count:
            lookup.count = int(len(out))
            lookup.total = _spend_total(scoped)
        case Metric.average:
            lookup.count = int(len(out))
            lookup.total = _spend_total(scoped)
            lookup.average = _money(lookup.total / lookup.count) if lookup.count else None
        case Metric.largest | Metric.smallest:
            lookup.count = int(len(out))
            lookup.total = _spend_total(scoped)
            if not out.empty:
                row = out.loc[out["amount"].idxmin() if plan.metric == Metric.largest
                              else out["amount"].idxmax()]
                lookup.largest = MerchantAmount(merchant=str(row["display"]),
                                                amount=_money(abs(row["amount"])))
        case Metric.top_merchants | Metric.top_categories:
            column = "display" if plan.metric == Metric.top_merchants else "category"
            totals = out.groupby(column)["amount"].sum().abs().sort_values(ascending=False)
            lookup.total = _spend_total(scoped)
            lookup.count = int(len(out))
            lookup.items = [CategoryAmount(name=str(name), amount=_money(value))
                            for name, value in totals.head(limit).items()]
        case Metric.list_recurring:
            # Detected over completed months only: a price change in the current month would
            # otherwise disqualify a charge that is plainly still recurring.
            history = month_view(df, pd.Timestamp(plan.period.end)).history
            active = detect_recurring(history)
            keep = [r for r in active.values()
                    if plan.subject.kind != SubjectKind.category
                    or r.category.lower() == (plan.subject.value or "").lower()]
            keep.sort(key=lambda r: -r.median_amount)
            lookup.items = [CategoryAmount(name=r.display, amount=r.median_amount)
                            for r in keep[:10]]
            lookup.total = _money(sum(r.median_amount for r in keep))
            lookup.count = len(keep)
            lookup.empty = not keep
        case _:  # total_out and trend
            lookup.total = _spend_total(scoped)
            lookup.count = int(len(out))

    previous = prior_period(plan.period, today)
    if previous and plan.metric in (Metric.total_out, Metric.trend, Metric.count,
                                    Metric.average, Metric.total_in, Metric.net):
        prior_scoped = _subject_filter(_window(df, previous), plan.subject)
        prior = (_money(prior_scoped.loc[prior_scoped["amount"] > 0, "amount"].sum())
                 if plan.metric == Metric.total_in else _spend_total(prior_scoped))
        lookup.prior_total = prior
        lookup.delta_pct = _pct(lookup.total, prior)

    if plan.metric not in (Metric.list_recurring,):
        lookup.empty = lookup.count == 0
    return lookup
