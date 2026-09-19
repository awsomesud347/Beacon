"""Deterministic fallback narration, built directly from the bundle. Always correct.

Also used for discreet mode (no amounts spoken).
"""

from num2words import num2words

from backend.contract import Anomaly, AnomalyType, FactBundle, Intent, Verdict
from backend.narration import refusals


def money(x: float) -> str:
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def pct(x: float) -> str:
    return f"{abs(x):g}%"


def count(n: int) -> str:
    return num2words(n) if 0 <= n <= 20 else str(n)


def _names(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _updown(x: float | None) -> str:
    return "up" if (x or 0) >= 0 else "down"


def _anomaly(a: Anomaly, discreet: bool) -> str:
    m = _names(a.merchants)
    match a.type:
        case AnomalyType.new_recurring:
            if a.count == 1:
                return f"a new subscription, {m}" + ("" if discreet else f", for {money(a.total)}")
            if discreet:
                return f"{count(a.count)} new subscriptions, from {m}"
            return f"{count(a.count)} new subscriptions totaling {money(a.total)}, from {m}"
        case AnomalyType.duplicate_charge:
            return (f"a possible duplicate charge at {m}" if discreet
                    else f"{m} charged you {money(a.amount)} twice, which may be a duplicate")
        case AnomalyType.amount_drift:
            return (f"{m} went {_updown(a.change_pct)} in price" if discreet
                    else f"{m} went from {money(a.previous_amount)} to {money(a.amount)}")
        case AnomalyType.missing_recurring:
            return (f"your usual {m} charge hasn't come through" if discreet
                    else f"your usual {m} charge of {money(a.amount)} hasn't come through")
        case AnomalyType.category_outlier:
            direction = "higher" if (a.change_pct or 0) >= 0 else "lower"
            if discreet:
                return f"{a.category} spending is {direction} than usual"
            return (f"{a.category} spending is {money(a.amount)}, {_updown(a.change_pct)} "
                    f"{pct(a.change_pct or 0)} on your usual {money(a.typical_amount)}")
        case AnomalyType.large_transaction:
            return f"a large purchase at {m}" + ("" if discreet else f" of {money(a.amount)}")
    return ""


def _anomalies(b: FactBundle, discreet: bool) -> str:
    if b.verdict == Verdict.no_data:
        return refusals.NO_DATA
    if not b.anomalies:
        return f"Nothing stands out in {b.period}. Your spending looks normal."
    n = len(b.anomalies)
    lead = ("Your spending is normal except for "
            if b.verdict != Verdict.unusual else "This month looks unusual overall, with ")
    lead += "one thing: " if n == 1 else f"{count(n)} things: "
    parts = [_anomaly(a, discreet) for a in b.anomalies]
    body = parts[0] if n == 1 else "; ".join(parts[:-1]) + "; and " + parts[-1]
    return lead + body + "."


def _summary(b: FactBundle, discreet: bool) -> str:
    c = b.context
    if discreet:
        trend = "more than" if c.delta_pct > 0 else "less than" if c.delta_pct < 0 else "about"
        s = f"In {b.period} you've spent {trend} last month."
    else:
        s = (f"In {b.period} you've spent {money(c.month_total_out)}, "
             f"{_updown(c.delta_pct)} {pct(c.delta_pct)} from last month.")
    if b.anomalies:
        s += " One thing stands out: " + _anomaly(b.anomalies[0], discreet) + "."
    elif b.verdict == Verdict.normal:
        s += " Nothing unusual stands out."
    return s


def _where(b: FactBundle, discreet: bool) -> str:
    top = (b.summary.top_categories if b.summary else [])[:3]
    if not top:
        return refusals.NO_DATA
    if discreet:
        return f"Your biggest categories in {b.period} were {_names([c.name for c in top])}."
    items = [f"{c.name} at {money(c.amount)}" for c in top]
    return (f"In {b.period} you've spent {money(b.context.month_total_out)}. "
            f"The biggest categories were {_names(items)}.")


def _compare(b: FactBundle, discreet: bool) -> str:
    cmp = b.comparison
    if cmp is None:
        return refusals.NO_DATA
    if discreet:
        trend = "more" if cmp.delta_pct > 0 else "less" if cmp.delta_pct < 0 else "about the same"
        s = f"You've spent {trend} than last month."
        if cmp.biggest_increase:
            s += f" The biggest increase is {cmp.biggest_increase.name}."
        return s
    s = (f"You've spent {money(cmp.current_total_out)} this month compared with "
         f"{money(cmp.prior_total_out)} last month, {_updown(cmp.delta_pct)} {pct(cmp.delta_pct)}.")
    if cmp.biggest_increase and cmp.biggest_increase.delta_pct is not None:
        s += (f" The biggest increase is {cmp.biggest_increase.name}, "
              f"up {pct(cmp.biggest_increase.delta_pct)}.")
    if cmp.biggest_decrease and cmp.biggest_decrease.delta_pct is not None:
        s += (f" The biggest drop is {cmp.biggest_decrease.name}, "
              f"down {pct(cmp.biggest_decrease.delta_pct)}.")
    return s


def render(bundle: FactBundle, discreet: bool = False) -> str:
    match bundle.query_type:
        case Intent.anomalies:
            return _anomalies(bundle, discreet)
        case Intent.month_summary:
            return _summary(bundle, discreet)
        case Intent.where_money_went:
            return _where(bundle, discreet)
        case Intent.compare_last_month:
            return _compare(bundle, discreet)
    return refusals.UNKNOWN
