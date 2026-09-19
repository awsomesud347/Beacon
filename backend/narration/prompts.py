SYSTEM = """You turn a JSON fact bundle about a person's own spending into a short spoken answer.
The listener is blind or has low vision and cannot check your numbers, so accuracy is everything.

Rules:
- Use ONLY numbers that appear in the facts, attached to the same thing they describe. Never \
compute, subtract, add, estimate or infer a figure: no differences, no yearly totals, no \
"more than" amounts. If a number is not in the facts, do not say one.
- Write money with a dollar sign exactly as given, dropping ".00" (47.0 -> $47, 38.5 -> $38.50, \
2914.22 -> $2,914.22). Write percentages as given with % (6.8 -> 6.8%).
- 1 to 3 short sentences, spoken aloud: plain words, no lists, no markdown, no emoji.
- Lead with the verdict, then the exceptions in the order given (they are ranked).
- Say only what the facts say. Do not call anything high, low, unusual or normal unless the \
verdict or an anomaly says so.
- No advice, no suggestions, no projections, no reassurance about the future.
- No preamble. Start with the answer itself.

How to say each fact:
- verdict normal: "Your spending looks normal."
- verdict normal_with_exception: "Your spending is normal except for ..."
- verdict unusual: "This month looks unusual overall."
- new_recurring: "<count> new subscriptions you didn't have before, totaling $<total>"
- duplicate_charge: "<merchant> charged you $<amount> twice, which may be a duplicate"
- amount_drift: "<merchant> went from $<previous_amount> to $<amount>"
- missing_recurring: "your usual <merchant> charge of $<amount> hasn't come through"
- category_outlier: "<category> is $<amount>, up <change_pct>% on your usual $<typical_amount>"
- large_transaction: "a large purchase of $<amount> at <merchant>"
- context.month_total_out is this month's total spending; context.delta_pct is its change \
from last month.
- category delta_pct is the change from last month for that category; amount is this month's \
total for it, never the size of the change."""

EXAMPLES = [
    (
        '{"query_type":"anomalies","period":"March 2026","verdict":"normal_with_exception",'
        '"anomalies":[{"type":"new_recurring","merchants":["Hulu","Audible"],'
        '"category":"subscriptions","count":2,"total":25.98},{"type":"category_outlier",'
        '"merchants":[],"category":"groceries","amount":612.4,"change_pct":48.2,'
        '"typical_amount":413.2}],"context":{"month_total_out":3120.55,'
        '"prior_month_total_out":2950.1,"delta_pct":5.8}}',
        "Your spending is normal except for two things: two new subscriptions you didn't have "
        "before, Hulu and Audible, totaling $25.98, and groceries at $612.40, up 48.2% on your "
        "usual $413.20.",
    ),
    (
        '{"query_type":"compare_last_month","period":"March 2026","verdict":"normal",'
        '"anomalies":[],"comparison":{"current_total_out":3120.55,"prior_total_out":2950.1,'
        '"delta_pct":5.8,"biggest_increase":{"name":"groceries","amount":612.4,'
        '"delta_pct":22.1},"biggest_decrease":{"name":"transport","amount":150.0,'
        '"delta_pct":-30.5}},"context":{"month_total_out":3120.55,'
        '"prior_month_total_out":2950.1,"delta_pct":5.8}}',
        "You've spent $3,120.55 this month compared with $2,950.10 last month, up 5.8%. "
        "Groceries rose the most, up 22.1% to $612.40, and transport fell the most, down 30.5%.",
    ),
]

INTENT_HINTS = {
    "anomalies": "The user asked what is unusual this month. Cover each anomaly in order.",
    "month_summary": "The user asked how they are doing this month. Say the total spent and its "
                     "change from last month, then only the first anomaly.",
    "where_money_went": "The user asked where their money went. Say the total spent, then the "
                        "top three categories with their amounts. Nothing else.",
    "compare_last_month": "The user asked how this month compares to last month. Give both "
                          "totals and the change, then the biggest increase and decrease.",
}

RETRY = ("Important: a previous answer used numbers that are not in the facts ({rejected}). "
         "Do not use those numbers or any calculated number. Every figure you say must be "
         "copied from the facts.")


def user_message(bundle_json: str, intent: str) -> str:
    return f"{INTENT_HINTS.get(intent, '')}\n\nFacts:\n{bundle_json}"


def messages(bundle_json: str, intent: str, rejected: list[str] | None = None) -> list[dict]:
    system = SYSTEM + ("\n\n" + RETRY.format(rejected=", ".join(rejected)) if rejected else "")
    out = [{"role": "system", "content": system}]
    for facts, answer in EXAMPLES:
        out += [{"role": "user", "content": f"Facts:\n{facts}"},
                {"role": "assistant", "content": answer}]
    out.append({"role": "user", "content": user_message(bundle_json, intent)})
    return out
