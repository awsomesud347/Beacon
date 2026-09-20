"""The data pack: everything the model is allowed to know about this ledger, precomputed.

The model never sees a transaction. It sees these aggregates, and every figure it speaks is
checked back against them, so it can talk freely about the data without being able to invent
a number. Keep it compact — it ships with every narration call.
"""

import pandas as pd

from backend.analysis.loader import period_label
from backend.analysis.rules import _outflows, category_totals, detect_all, detect_recurring
from backend.contract import (
    CategoryAmount,
    MerchantAmount,
    MonthTotals,
    Overview,
)

MONTHS_OF_HISTORY = 6
TOP_CATEGORIES = 8
TOP_MERCHANTS = 8
TOP_ANOMALIES = 3


def _money(x: float) -> float:
    return round(float(x), 2)


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def build(df: pd.DataFrame) -> Overview:
    """A months-by-categories summary of the whole ledger, plus what stands out."""
    frame = df.copy()
    frame["period"] = frame["date"].dt.to_period("M")
    as_of = frame["date"].max()
    current = as_of.to_period("M")
    periods = [current - i for i in range(MONTHS_OF_HISTORY - 1, -1, -1)]

    table = category_totals(frame[frame["period"].isin(periods)]).reindex(periods, fill_value=0)
    months = []
    for period in periods:
        window = frame[frame["period"] == period]
        out = _outflows(window)
        months.append(MonthTotals(
            period=period_label(period.start_time),
            total_out=_money(out["amount"].abs().sum()),
            total_in=_money(window.loc[window["amount"] > 0, "amount"].sum()),
            transactions=int(len(out)),
        ))

    current_row = table.loc[current] if current in table.index else None
    prior = current - 1
    prior_row = table.loc[prior] if prior in table.index else None
    categories = []
    if current_row is not None:
        ranked = current_row.sort_values(ascending=False).head(TOP_CATEGORIES)
        for name, amount in ranked.items():
            previous = float(prior_row[name]) if prior_row is not None else 0.0
            categories.append(CategoryAmount(name=str(name), amount=_money(amount),
                                             delta_pct=_pct(float(amount), previous)))

    current_frame = frame[frame["period"] == current]
    merchant_totals = (_outflows(current_frame).groupby("display")["amount"].sum().abs()
                       .sort_values(ascending=False).head(TOP_MERCHANTS))
    merchants = [MerchantAmount(merchant=str(name), amount=_money(value))
                 for name, value in merchant_totals.items()]

    recurring = sorted(detect_recurring(frame[frame["period"] < current]).values(),
                       key=lambda r: -r.median_amount)
    findings = detect_all(df)

    return Overview(
        current_period=period_label(as_of),
        as_of=as_of.date(),
        months=months,
        categories_this_period=categories,
        merchants_this_period=merchants,
        recurring=[CategoryAmount(name=r.display, amount=r.median_amount) for r in recurring],
        anomalies=[f.anomaly for f in findings[:TOP_ANOMALIES]],
        all_categories=sorted(str(c) for c in df["category"].dropna().unique()),
    )
