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
- Always a complete sentence with a verb ("you made 13 purchases", not "13 purchases").
- Spell category and shop names exactly as the facts spell them ("Kroger", not "kroger").

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
        '{"query_type":"lookup","period":"July 2026","verdict":"normal","anomalies":[],'
        '"plan":{"metric":"total_out","subject":{"kind":"category","value":"groceries"},'
        '"period":{"kind":"named_month","label":"July 2026"}},'
        '"lookup":{"subject_label":"groceries","period_label":"July 2026","total":412.0,'
        '"count":9,"prior_total":389.5,"prior_label":"June 2026","delta_pct":5.8},'
        '"understood":"groceries in July 2026"}',
        "You spent $412 across 9 purchases, up 5.8% from June 2026.",
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

LOOKUP_HINT = """`plan` says what was asked; `lookup` holds the figures for exactly that;
`overview` is background about the whole ledger. Answer the question that `plan` describes.
Start with the answer itself. Do NOT open by naming the category, shop or month — that
opening is added for you, and writing your own is how the wrong label gets attached to the
right number.
If `empty` is true, say plainly that nothing was spent there — never substitute another figure.
Never attach a figure to a category or shop the question was not about."""

# What shape of answer each kind of question needs. Without this a list question gets
# answered with one item's number, which sounds confident and is wrong.
METRIC_HINTS = {
    "total_out": "Give lookup.total, and the change from prior_label if delta_pct is there.",
    "total_in": "Give lookup.total as money received.",
    "net": "lookup.total is what was LEFT OVER after spending — not what came in. Say that "
           "amount as kept (or overspent if negative), then items 'money in' and "
           "'money out'.",
    "count": "Lead with lookup.count as the number of purchases, then lookup.total.",
    "average": "Give lookup.average, then how many purchases it averages over.",
    "largest": "Name lookup.largest.merchant and its amount.",
    "smallest": "Name lookup.largest.merchant and its amount as the smallest purchase.",
    "trend": "Say up or down by delta_pct, then lookup.total against prior_total in "
             "prior_label.",
    "list_recurring": "Say how many regular charges and their monthly total, then name them "
                      "from lookup.items. This is a list of charges, not a count of "
                      "purchases.",
    "top_categories": "Name the top categories from lookup.items WITH their amounts, in "
                      "order. Do not single out one category.",
    "top_merchants": "Name the top shops from lookup.items WITH their amounts, in order. "
                     "Do not single out one shop.",
    "summary": "Give context.month_total_out and how it compares with "
               "context.prior_month_total_out using context.delta_pct, then mention at most "
               "one item from anomalies. This is the whole month, not one category.",
    "anomalies": "Lead with the verdict, then each entry in anomalies, in order.",
}

INTENT_HINTS = {
    "lookup": LOOKUP_HINT,
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


def user_message(bundle_json: str, intent: str, metric: str | None = None) -> str:
    hint = INTENT_HINTS.get(intent, "")
    if metric and metric in METRIC_HINTS:
        hint = f"{hint}\n{METRIC_HINTS[metric]}"
    return f"{hint}\n\nFacts:\n{bundle_json}"


def messages(bundle_json: str, intent: str, rejected: list[str] | None = None,
             metric: str | None = None) -> list[dict]:
    system = SYSTEM + ("\n\n" + RETRY.format(rejected=", ".join(rejected)) if rejected else "")
    out = [{"role": "system", "content": system}]
    for facts, answer in EXAMPLES:
        out += [{"role": "user", "content": f"Facts:\n{facts}"},
                {"role": "assistant", "content": answer}]
    out.append({"role": "user", "content": user_message(bundle_json, intent, metric)})
    return out
