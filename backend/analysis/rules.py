"""Deterministic detection rules (build-spec §4). Pure functions over the normalized ledger.
Zero LLM involvement: everything here is arithmetic on the DataFrame."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.contract import Anomaly, AnomalyType

NON_SPEND = {"income", "transfer"}
FIXED_CATEGORIES = {"rent"}  # never a category outlier; changes surface via recurring rules
RECURRING_TYPES = {AnomalyType.new_recurring, AnomalyType.amount_drift,
                   AnomalyType.missing_recurring}

# Severity = dollar impact x novelty weight. Recurring changes are annualized.
WEIGHTS = {
    AnomalyType.new_recurring: 1.5,
    AnomalyType.duplicate_charge: 3.0,
    AnomalyType.amount_drift: 1.2,
    AnomalyType.missing_recurring: 0.3,
    AnomalyType.category_outlier: 1.0,
    AnomalyType.large_transaction: 0.8,
}


@dataclass
class Finding:
    anomaly: Anomaly
    severity: float
    z_score: float | None = None


@dataclass
class Recurring:
    display: str
    category: str
    median_amount: float
    typical_day: int
    last_seen: pd.Timestamp


@dataclass
class MonthView:
    df: pd.DataFrame
    as_of: pd.Timestamp
    period: pd.Period
    current: pd.DataFrame
    history: pd.DataFrame


def month_view(df: pd.DataFrame, as_of: pd.Timestamp | None = None) -> MonthView:
    df = df.copy()
    df["period"] = df["date"].dt.to_period("M")
    as_of = as_of or df["date"].max()
    period = as_of.to_period("M")
    return MonthView(
        df=df,
        as_of=as_of,
        period=period,
        current=df[(df["period"] == period) & (df["date"] <= as_of)],
        history=df[df["period"] < period],
    )


def _money(x: float) -> float:
    return round(float(x), 2)


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def _outflows(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["amount"] < 0) & ~df["category"].isin(NON_SPEND)]


# --- Rules -------------------------------------------------------------------


def detect_recurring(history: pd.DataFrame) -> dict[str, Recurring]:
    """Merchant seen >=3 times, inter-arrival ~28-32 days, amount within +-10%."""
    found: dict[str, Recurring] = {}
    for display, g in _outflows(history).groupby("display"):
        if len(g) < 3:
            continue
        g = g.sort_values("date")
        gaps = g["date"].diff().dt.days.dropna()
        amounts = g["amount"].abs()
        median = float(amounts.median())
        if not (28 <= gaps.median() <= 32 and gaps.between(25, 35).all()):
            continue
        if not ((amounts - median).abs() <= 0.10 * median).all():
            continue
        found[display] = Recurring(
            display=display,
            category=str(g["category"].mode().iloc[0]),
            median_amount=_money(median),
            typical_day=int(g["date"].dt.day.median()),
            last_seen=g["date"].max(),
        )
    return found


def new_recurring(view: MonthView) -> list[Finding]:
    """Subscription-type charges this month from merchants absent in the prior 3 months."""
    prior = view.history[view.history["period"] >= view.period - 3]
    seen = set(prior["display"])
    cur = _outflows(view.current)
    new = cur[(cur["category"] == "subscriptions") & ~cur["display"].isin(seen)]
    if new.empty:
        return []
    merchants = list(dict.fromkeys(new.sort_values("date")["display"]))
    total = _money(new["amount"].abs().sum())
    anomaly = Anomaly(type=AnomalyType.new_recurring, merchants=merchants,
                      category="subscriptions", count=len(merchants), total=total)
    return [Finding(anomaly, total * 12 * WEIGHTS[AnomalyType.new_recurring])]


def missing_recurring(view: MonthView, recurring: dict[str, Recurring]) -> list[Finding]:
    """Recurring charge active last month, overdue by >3 days this month."""
    out = []
    charged = set(view.current["display"])
    last_month = view.period - 1
    for r in recurring.values():
        if r.last_seen.to_period("M") != last_month or r.display in charged:
            continue
        expected = view.period.start_time + pd.Timedelta(days=r.typical_day - 1)
        if expected + pd.Timedelta(days=3) > view.as_of:
            continue
        anomaly = Anomaly(type=AnomalyType.missing_recurring, merchants=[r.display],
                          category=r.category, amount=r.median_amount)
        out.append(Finding(anomaly, r.median_amount * 12 * WEIGHTS[anomaly.type]))
    return out


def amount_drift(view: MonthView, recurring: dict[str, Recurring]) -> list[Finding]:
    """Recurring charge changed >10% vs its own trailing median."""
    out = []
    cur = _outflows(view.current)
    for r in recurring.values():
        charges = cur[cur["display"] == r.display]
        if charges.empty:
            continue
        amount = _money(charges["amount"].abs().iloc[-1])
        if abs(amount - r.median_amount) <= 0.10 * r.median_amount:
            continue
        anomaly = Anomaly(type=AnomalyType.amount_drift, merchants=[r.display],
                          category=r.category, amount=amount, previous_amount=r.median_amount,
                          change_pct=_pct(amount, r.median_amount))
        impact = abs(amount - r.median_amount) * 12
        out.append(Finding(anomaly, impact * WEIGHTS[anomaly.type]))
    return out


def duplicate_charge(view: MonthView) -> list[Finding]:
    """Same merchant + same amount within 48 hours.

    Fixed-price habits (a $2.75 transit fare seen 3+ times before) are not duplicates.
    """
    out = []
    habitual = _outflows(view.history).groupby(["display", "amount"]).size()
    habitual = set(habitual[habitual >= 3].index)
    cur = _outflows(view.current).sort_values("date")
    for (display, amount), g in cur.groupby(["display", "amount"]):
        if (display, amount) in habitual:
            continue
        if len(g) < 2 or g["date"].diff().dt.days.dropna().min() > 2:
            continue
        amt = _money(abs(amount))
        anomaly = Anomaly(type=AnomalyType.duplicate_charge, merchants=[display],
                          category=str(g["category"].iloc[0]), count=len(g), amount=amt,
                          total=_money(amt * len(g)))
        out.append(Finding(anomaly, amt * WEIGHTS[anomaly.type]))
    return out


def category_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Outflow totals per (period, category) as positive magnitudes; missing months = 0."""
    out = _outflows(df)
    table = out.pivot_table(index="period", columns="category", values="amount", aggfunc="sum")
    return table.fillna(0).abs()


def category_outlier(view: MonthView, explained: set[str]) -> list[Finding]:
    """Category month total with |z| > 2 vs the trailing 6 months."""
    trailing_periods = [view.period - i for i in range(6, 0, -1)]
    table = category_totals(view.df[view.df["period"].isin([*trailing_periods, view.period])])
    table = table.reindex([*trailing_periods, view.period], fill_value=0)
    out = []
    for category in table.columns:
        if category in FIXED_CATEGORIES or category in explained:
            continue
        trailing = table.loc[trailing_periods, category]
        std = float(trailing.std(ddof=1))
        if std == 0:
            continue
        mean = float(trailing.mean())
        current = float(table.loc[view.period, category])
        z = (current - mean) / std
        if abs(z) <= 2 or abs(current - mean) < 25:
            continue
        anomaly = Anomaly(type=AnomalyType.category_outlier, category=category,
                          amount=_money(current), typical_amount=_money(mean),
                          change_pct=_pct(current, mean))
        out.append(Finding(anomaly, abs(current - mean) * WEIGHTS[anomaly.type], z_score=z))
    return out


def large_transaction(view: MonthView, recurring: dict[str, Recurring]) -> list[Finding]:
    """One-off purchase above p95 of the trailing 12 months' largest monthly one-off purchase.

    (A plain p95 over all transactions flags ~5% of every month by construction.)
    """
    def one_offs(df: pd.DataFrame) -> pd.DataFrame:
        out = _outflows(df)
        return out[~out["display"].isin(recurring) & ~out["category"].isin(FIXED_CATEGORIES)]

    trailing = one_offs(view.history[view.history["period"] >= view.period - 12])
    if trailing.empty:
        return []
    monthly_max = trailing.groupby("period")["amount"].min().abs()
    threshold = float(np.percentile(monthly_max, 95))
    out = []
    for _, row in one_offs(view.current).iterrows():
        amount = abs(float(row["amount"]))
        if amount <= threshold:
            continue
        anomaly = Anomaly(type=AnomalyType.large_transaction, merchants=[row["display"]],
                          category=row["category"], amount=_money(amount))
        out.append(Finding(anomaly, amount * WEIGHTS[anomaly.type]))
    return out


def detect_all(df: pd.DataFrame, as_of: pd.Timestamp | None = None) -> list[Finding]:
    """Run every rule and return findings ranked by severity (highest first)."""
    view = month_view(df, as_of)
    if view.current.empty:
        return []
    recurring = detect_recurring(view.history)
    findings = [
        *new_recurring(view),
        *missing_recurring(view, recurring),
        *amount_drift(view, recurring),
        *duplicate_charge(view),
        *large_transaction(view, recurring),
    ]
    explained = {f.anomaly.category for f in findings
                 if f.anomaly.type in RECURRING_TYPES and f.anomaly.category}
    findings += category_outlier(view, explained)
    return sorted(findings, key=lambda f: f.severity, reverse=True)
