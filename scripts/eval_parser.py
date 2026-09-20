"""Question understanding eval: how many real questions does Beacon answer correctly?

Separates the two failure modes, which are not equally bad:
  - "don't know"  honest, safe; the user can rephrase
  - MISROUTE      a fluent answer to a different question; the dangerous one

Usage:
  uv run python scripts/eval_parser.py            # patterns + model parser
  uv run python scripts/eval_parser.py --patterns # deterministic only, no model
"""

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import service, state  # noqa: E402
from backend.contract import SubjectKind  # noqa: E402

# (question, expected intent, expected metric or None, expected subject or None)
BANK: list[tuple[str, str, str | None, str | None]] = [
    # --- the rehearsed demo questions
    ("what's unusual?", "anomalies", None, None),
    ("anything I should know about this month?", "anomalies", None, None),
    ("how am I doing this month?", "month_summary", None, None),
    ("how's my month going?", "month_summary", None, None),
    ("where did my money go?", "where_money_went", None, None),
    ("how does this compare to last month?", "compare_last_month", None, None),
    # --- category spend, plain and paraphrased
    ("how much did I spend on groceries?", "lookup", "total_out", "groceries"),
    ("what have I spent on groceries?", "lookup", "total_out", "groceries"),
    ("how much am I dropping on eating out?", "lookup", "total_out", "dining"),
    ("what's my coffee habit costing me?", "lookup", "total_out", "coffee"),
    ("how much on dining out?", "lookup", "total_out", "dining"),
    ("how much do I spend on gas?", "lookup", "total_out", "transport"),
    ("am I spending a lot on coffee?", "lookup", "total_out", "coffee"),
    ("what's my rent?", "lookup", "total_out", "rent"),
    ("how much goes to utilities?", "lookup", "total_out", "utilities"),
    ("what do I spend on subscriptions?", "lookup", "total_out", "subscriptions"),
    # --- merchants
    ("what did I spend at Kroger?", "lookup", "total_out", "Kroger"),
    ("did Netflix charge me this month?", "lookup", "total_out", "Netflix"),
    ("anything from Amazon lately?", "lookup", "total_out", "Amazon"),
    ("how much have I given Starbucks?", "lookup", "total_out", "Starbucks"),
    ("am I still paying Planet Fitness?", "lookup", "total_out", "Planet Fitness"),
    # --- time ranges
    ("how much did I spend in July?", "lookup", "total_out", None),
    ("what did I spend last month?", "lookup", "total_out", None),
    ("how much this week?", "lookup", "total_out", None),
    ("how much in the last 30 days?", "lookup", "total_out", None),
    ("what did I spend yesterday?", "lookup", "total_out", None),
    ("how much this year?", "lookup", "total_out", None),
    ("how much on groceries in July?", "lookup", "total_out", "groceries"),
    # --- counts, averages, superlatives, lists
    ("how many times did I eat out?", "lookup", "count", "dining"),
    ("how often do I buy coffee?", "lookup", "count", "coffee"),
    ("what's my average grocery trip?", "lookup", "average", "groceries"),
    ("what was my biggest purchase?", "lookup", "largest", None),
    ("what's the most expensive thing I bought?", "lookup", "largest", None),
    ("what subscriptions do I have?", "lookup", "list_recurring", "subscriptions"),
    ("what are my recurring charges?", "lookup", "list_recurring", None),
    ("where do I shop the most?", "lookup", "top_merchants", None),
    ("which categories are biggest?", "lookup", "top_categories", None),
    # --- income, net, trend
    ("how much did I make this month?", "lookup", "total_in", None),
    ("did I get paid?", "lookup", "total_in", None),
    ("am I saving money?", "lookup", "net", None),
    ("what came in versus what went out?", "lookup", "net", None),
    ("is my dining spending going up?", "lookup", "trend", "dining"),
    ("has my grocery bill changed?", "lookup", "trend", "groceries"),
    # --- speech-to-text noise (what the agent actually hands us)
    ("how much did i spend on grocerys", "lookup", "total_out", "groceries"),
    ("whats unusual", "anomalies", None, None),
    ("how much at croger", "lookup", "total_out", "Kroger"),
    ("wheres my money going", "where_money_went", None, None),
    ("how much did i spend on eating out last month", "lookup", "total_out", "dining"),
    # --- refusals and chat
    ("should I cancel Netflix?", "advice_refused", None, None),
    ("can I afford a vacation?", "advice_refused", None, None),
    ("do you think I spend too much?", "advice_refused", None, None),
    ("who are you?", "identity", None, None),
    ("is this real data?", "identity", None, None),
    ("what can I ask you?", "help", None, None),
    ("repeat that", "replay", None, None),
    # --- honestly unanswerable
    ("what's my bank balance?", "unsupported", None, None),
    ("how much on pets?", "unsupported", None, None),
    ("transfer $50 to my sister", "unsupported", None, None),
    ("what will I spend next month?", "advice_refused", None, None),
    ("what's the weather?", "unsupported", None, None),
]

FOLLOW_UPS: list[tuple[str, str, str | None, str | None]] = [
    ("how much on groceries?", "lookup", "total_out", "groceries"),
    ("what about last month?", "lookup", "total_out", "groceries"),
    ("and dining?", "lookup", "total_out", "dining"),
    ("how about at Kroger?", "lookup", "total_out", "Kroger"),
]


def check(question, want_intent, want_metric, want_subject, use_parser):
    started = time.perf_counter()
    routed = service.resolve(question, use_parser=use_parser)
    elapsed = (time.perf_counter() - started) * 1000
    got_intent = routed.intent.value
    plan = routed.plan

    if got_intent != want_intent:
        # Honest refusals are safe; anything else is a confident wrong answer.
        safe = got_intent in ("unknown", "unsupported") and want_intent != "advice_refused"
        return ("don't know" if safe else "MISROUTE"), got_intent, elapsed
    if want_metric and plan and plan.metric.value != want_metric:
        return "MISROUTE", f"{got_intent}/{plan.metric.value}", elapsed
    if want_subject and plan and (plan.subject.value or "") != want_subject:
        return "MISROUTE", f"{got_intent}/{plan.subject.value}", elapsed
    if want_subject is None and plan and plan.subject.kind != SubjectKind.all and want_metric:
        return "MISROUTE", f"{got_intent}/{plan.subject.value}", elapsed
    return "correct", got_intent, elapsed


def main(use_parser: bool) -> int:
    state.load_default()
    mode = "patterns + model parser" if use_parser else "patterns only (no model)"
    print(f"Question understanding eval — {mode}\n")

    outcomes: Counter[str] = Counter()
    latencies: list[float] = []
    problems: list[str] = []

    for question, intent, metric, subject in BANK:
        state.state.last_plan = None
        verdict, got, ms = check(question, intent, metric, subject, use_parser)
        outcomes[verdict] += 1
        latencies.append(ms)
        if verdict != "correct":
            problems.append(f"  {verdict:<11} {question:<48} got {got}, wanted {intent}")

    state.state.last_plan = None
    for question, intent, metric, subject in FOLLOW_UPS:  # sequential: context matters
        verdict, got, ms = check(question, intent, metric, subject, use_parser)
        outcomes[verdict] += 1
        latencies.append(ms)
        if verdict != "correct":
            problems.append(f"  {verdict:<11} {question:<48} got {got}, wanted {intent}")
        if routed_plan := service.resolve(question, use_parser=use_parser).plan:
            state.state.last_plan = routed_plan

    total = sum(outcomes.values())
    unsure = outcomes["don't know"]
    print(f"correct:      {outcomes['correct']}/{total}")
    print(f"don't know:   {unsure}   (honest, safe)")
    print(f"MISROUTES:    {outcomes['MISROUTE']}   (answered a different question)")
    latencies.sort()
    print(f"median routing time: {latencies[len(latencies) // 2]:.0f} ms   "
          f"slowest: {latencies[-1]:.0f} ms")
    if problems:
        print("\n" + "\n".join(problems))
    return 1 if outcomes["MISROUTE"] else 0


if __name__ == "__main__":
    raise SystemExit(main(use_parser="--patterns" not in sys.argv))
