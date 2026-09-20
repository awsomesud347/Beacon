"""Deterministic fallback narration, built directly from the bundle. Always correct.

Also used for discreet mode (no amounts spoken).
"""

import re

from num2words import num2words

from backend.contract import Anomaly, AnomalyType, FactBundle, Intent, Metric, Verdict
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


def read_back_lead(b: FactBundle) -> str:
    """The deterministic opening that tells the listener how the question was taken.

    Written here, never by the model: it kept copying the subject out of a prompt example
    and pinning it to whatever figures it had.
    """
    if not b.understood:
        return ""
    scoped = bool(b.plan and b.plan.subject.value)
    return f"For {b.understood}," if scoped else f"In {b.understood},"


def with_read_back(b: FactBundle, text: str) -> str:
    """Put our own read-back in front of the model's sentence, unless the sentence already
    says which subject and period it is about — two read-backs is worse than none."""
    lead = read_back_lead(b)
    if not lead or text.lower().startswith(("for ", "in ")):
        return text
    opening = text[:60].lower()
    subject = (b.plan.subject.value or "").lower() if b.plan else ""
    period = (b.lookup.period_label or "").lower() if b.lookup else ""
    if subject and subject in opening and (not period or period in text.lower()):
        return text[0].upper() + text[1:]
    return f"{lead} {text[0].lower()}{text[1:]}"


def _lookup(b: FactBundle, discreet: bool) -> str:
    """One deterministic sentence per metric. Always correct, used as the guard's fallback."""
    lk, plan = b.lookup, b.plan
    if lk is None or plan is None:
        return refusals.UNKNOWN
    # The two broad questions keep their own wording even when they arrive as a plan.
    if plan.metric == Metric.anomalies:
        return _anomalies(b, discreet)
    if plan.metric == Metric.summary:
        return _summary(b, discreet)
    scoped = lk.subject_label != "everything"
    what = lk.subject_label
    when = lk.period_label
    when = (when if when.startswith(("this", "last", "the", "yesterday", "today"))
            else f"in {when}")
    # When the answer opens by reading the question back, the sentence must not repeat the
    # subject and period again.
    read_back = bool(b.understood)
    on_what = "" if read_back or not scoped else f" on {what}"
    if read_back:
        when = ""


    change = ""
    if not discreet and lk.delta_pct is not None and plan.metric in (
            Metric.total_out, Metric.trend, Metric.total_in):
        against = lk.prior_label or "the period before"
        change = (f", the same as {against}" if lk.delta_pct == 0
                  else f", {_updown(lk.delta_pct)} {pct(lk.delta_pct)} from {against}")

    def sentence() -> str:
        if lk.empty and plan.metric != Metric.net:
            return f"you haven't spent anything{on_what} {when}."
        match plan.metric:
            case Metric.count:
                tail = "" if discreet else f", totaling {money(lk.total)}"
                subject = f"{what} " if scoped else ""
                noun = "purchase" if lk.count == 1 else "purchases"
                return f"you made {count(lk.count)} {subject}{noun} {when}{tail}."
            case Metric.average:
                if discreet or lk.average is None:
                    return f"you made {count(lk.count)} purchases{on_what} {when}."
                return (f"your average{on_what} {when} was {money(lk.average)}, "
                        f"across {count(lk.count)} purchases.")
            case Metric.largest | Metric.smallest:
                if lk.largest is None:
                    return f"I don't have a purchase{on_what} {when}."
                size = "biggest" if plan.metric == Metric.largest else "smallest"
                if discreet:
                    return f"your {size} purchase {when} was at {lk.largest.merchant}."
                return (f"your {size} purchase {when} was {money(lk.largest.amount)} "
                        f"at {lk.largest.merchant}.")
            case Metric.total_in:
                if discreet:
                    return f"you had {count(lk.count)} deposits {when}."
                return f"you brought in {money(lk.total)} {when}{change}."
            case Metric.net:
                if discreet:
                    how = ("kept some of what came in" if lk.total >= 0
                           else "spent more than came in")
                    return f"you {how} {when}."
                direction = "kept" if lk.total >= 0 else "overspent by"
                inflow = next((i.amount for i in lk.items if i.name == "money in"), None)
                outflow = next((i.amount for i in lk.items if i.name == "money out"), None)
                detail = (f" {money(inflow)} came in and {money(outflow)} went out."
                          if inflow is not None and outflow is not None else "")
                return f"you {direction} {money(abs(lk.total))} {when}.{detail}"
            case Metric.list_recurring:
                if not lk.items:
                    return f"I don't see any regular charges {when}."
                names = _names([i.name for i in lk.items[:5]])
                more = "" if len(lk.items) <= 5 else f", and {count(len(lk.items) - 5)} more"
                noun = "subscriptions" if scoped else "regular charges"
                if discreet:
                    return f"you have {count(lk.count)} {noun}: {names}{more}."
                return (f"you have {count(lk.count)} {noun} totaling {money(lk.total)} "
                        f"a month: {names}{more}.")
            case Metric.top_merchants | Metric.top_categories:
                if not lk.items:
                    return f"I don't have anything{on_what} {when}."
                if plan.metric == Metric.top_merchants:
                    if discreet:
                        return (f"you spent the most at "
                                f"{_names([i.name for i in lk.items])} {when}.")
                    parts = [f"{i.name} at {money(i.amount)}" for i in lk.items]
                    return f"you spent the most {when} at {_names(parts)}."
                if discreet:
                    return (f"your biggest categories {when} were "
                            f"{_names([i.name for i in lk.items])}.")
                parts = [f"{i.name} at {money(i.amount)}" for i in lk.items]
                return f"your biggest categories {when} were {_names(parts)}."
            case Metric.trend:
                if lk.delta_pct is None or discreet:
                    return f"you spent {money(lk.total)}{on_what} {when}."
                direction = "up" if lk.delta_pct >= 0 else "down"
                subject = what if scoped else "your spending"
                return (f"{subject} is {direction} {pct(lk.delta_pct)} {when}, at "
                        f"{money(lk.total)} against {money(lk.prior_total)} "
                        f"in {lk.prior_label}.")
        if discreet:
            return f"you made {count(lk.count)} purchases{on_what} {when}."
        return f"you spent {money(lk.total)}{on_what} {when}{change}."

    body = re.sub(r"\s+([,.])", r"\1", " ".join(sentence().split()))
    if lead := read_back_lead(b):
        return f"{lead} {body}"
    return body[0].upper() + body[1:]


def render(bundle: FactBundle, discreet: bool = False) -> str:
    match bundle.query_type:
        case Intent.lookup:
            return _lookup(bundle, discreet)
        case Intent.anomalies:
            return _anomalies(bundle, discreet)
        case Intent.month_summary:
            return _summary(bundle, discreet)
        case Intent.where_money_went:
            return _where(bundle, discreet)
        case Intent.compare_last_month:
            return _compare(bundle, discreet)
    return refusals.UNKNOWN
