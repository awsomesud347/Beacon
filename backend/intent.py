"""Deterministic query router and slot filler.

The fast path: anything matched here costs no model call at all, which keeps the rehearsed
demo questions instant. Whatever it cannot place confidently is handed to the parser
(`backend/narration/parser.py`); a misrouted question would answer the wrong thing fluently,
which for a listener who cannot see the screen is as bad as a wrong number.
"""

import re
from dataclasses import dataclass
from datetime import timedelta

from backend.analysis import query
from backend.analysis.vocab import Vocabulary
from backend.contract import (
    Intent,
    Metric,
    Period,
    PeriodKind,
    PlanSource,
    QueryPlan,
    Subject,
)

# Phrases that mean "tell me a number", used to stop advice patterns swallowing
# plain factual questions ("how much do I spend on gas" is not advice).
FACTUAL = re.compile(r"\b(how much|how many|what did|what have|what's my|total|spent|spend|"
                     r"spending|paid|pay|cost|charge[ds]?|anything from|anything at)\b")
# Narrower: the question is asking for an amount, not just mentioning charges.
SPEND_AMOUNT = re.compile(r"\b(how much|what do i spend|what did i spend|spent|cost|total)\b")

ADVICE = re.compile(
    r"\b(should i|shall i|can i afford|could i afford|am i going to|would it be|"
    r"is it (a )?(good|bad|smart|wise)|do you recommend|recommend|give me advice|advise|"
    r"worth it|what if i|how (much|can) (should|do) i (save|budget)|help me (save|budget|plan))\b")
# Advice even when the sentence also contains spending words: opinions and predictions.
STRONG_ADVICE = re.compile(
    r"\b(do you think|too much|too little|should i|shall i|can i afford|could i afford|"
    r"what will i|will i (be|have|spend)|next (month|week|year)|am i going to|"
    r"how am i going to)\b")
# Understood, but not something a transaction history can answer.
OUT_OF_SCOPE = re.compile(
    r"\b(balance|transfer|send money|move money|pay (my|the|this)|wire|withdraw|deposit money|"
    r"weather|news|stocks?|crypto|credit score|interest rate|read me my transactions|"
    r"list (all )?(my )?transactions)\b")
REPLAY = re.compile(r"\b(repeat|say (that|it) again|again please|replay|what did you (just )?say|"
                    r"come again|pardon)\b")
IDENTITY = re.compile(r"\b(who are you|what are you|is this real|real data|are you an ai|"
                      r"your name|who made you|is this my real)\b")
HELP = re.compile(r"\b(help|what can (you|i) (do|ask|tell)|what do you do|how does this work|"
                  r"what kind of questions|options)\b")
ANOMALIES = re.compile(r"\b(unusual|weird|strange|odd|anomal\w*|out of the ordinary|"
                       r"stand(s)? out|surpris\w*|suspicious|anything wrong|anything off|"
                       r"anything i should know|anything interesting|flag\w*)\b")
SUMMARY = re.compile(r"\b(how am i|how('m| am) i doing|how.{0,20}(doing|going|look)|"
                     r"summary|overview|status|am i (ok|okay|alright|fine))\b")
WHERE = re.compile(r"\b(where (did|does|has|is|'s) (my|the) money|where('s| is| did) it go|"
                   r"wheres my money|break ?down|what did i spend it on)\b")
COMPARE = re.compile(r"\b(compare[ds]?|comparison|versus|vs\.?|than last month)\b")

# Metric cues, checked before the generic intents.
METRIC_PATTERNS: list[tuple[Metric, re.Pattern[str]]] = [
    (Metric.list_recurring, re.compile(
        r"\b(subscriptions?|recurring|regular (charges|payments|bills)|memberships?|"
        r"what am i paying for)\b")),
    # Category/merchant rankings before "biggest", so "which categories are biggest"
    # is a ranking question and not a single largest purchase.
    (Metric.top_merchants, re.compile(
        r"\b(where do i (shop|spend)|which (shops?|stores?|merchants?)|top (shops?|stores?|"
        r"merchants?)|biggest (shops?|stores?|merchants?)|who do i pay)\b")),
    (Metric.top_categories, re.compile(
        r"\b(top categor\w+|biggest categor\w+|main categor\w+|which categor\w+|"
        r"categor\w+ are biggest)\b")),
    (Metric.largest, re.compile(
        r"\b(biggest|largest|most expensive|priciest|single biggest)\b")),
    (Metric.smallest, re.compile(r"\b(smallest|cheapest|least expensive)\b")),
    (Metric.count, re.compile(r"\b(how many|how often|number of times|how many times)\b")),
    (Metric.average, re.compile(r"\b(average|typical|on average|mean)\b")),
    # net before total_in: "what came in versus what went out" is a net question.
    (Metric.net, re.compile(
        r"\b(am i saving|saving money|net|left over|leftover|in versus out|in vs out|"
        r"came in.*went out|in.*versus.*out|put aside)\b")),
    (Metric.total_in, re.compile(
        r"\b(income|did i get paid|how much did i (make|earn)|paycheck|salary|came in|"
        r"money in)\b")),
    (Metric.trend, re.compile(
        r"\b(going up|going down|rising|increasing|decreasing|trend|creeping|"
        r"more than usual|less than usual|changed)\b")),
]

PERIOD_PATTERNS: list[tuple[PeriodKind, re.Pattern[str]]] = [
    (PeriodKind.last_month, re.compile(r"\blast month\b")),
    (PeriodKind.this_month, re.compile(r"\b(this month|so far this month|month to date)\b")),
    (PeriodKind.last_week, re.compile(r"\blast week\b")),
    (PeriodKind.this_week, re.compile(r"\b(this week|past week)\b")),
    (PeriodKind.this_year, re.compile(r"\b(this year|year to date|ytd)\b")),
    (PeriodKind.all_time, re.compile(r"\b(all time|ever|overall|in total|altogether)\b")),
]
LAST_N_DAYS = re.compile(r"\blast (\d{1,3}) days\b")
DAY_WORD = re.compile(r"\b(yesterday|today)\b")
NAMED_MONTH = re.compile(
    r"\b(in |during |for )?(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b"
    r"( (\d{4}))?")
# "on groceries", "at Kroger", "for coffee", "from Amazon"
SUBJECT_PHRASE = re.compile(
    r"\b(?:on|at|for|from|to|with|about)\s+([a-z0-9'&.\- ]{2,40}?)"
    r"(?=\s+(?:in|during|this|last|over|since|for|ever|yet|so far)\b|[?.,!]|$)")
FOLLOWUP = re.compile(r"^\s*(and|what about|how about|ok(ay)? (and|what about)|also)\b[\s,]*")


@dataclass
class Routed:
    """Either a finished intent, or a plan to execute. `plan` is None for fixed answers."""

    intent: Intent
    plan: QueryPlan | None = None
    inferred: bool = False  # something was guessed or carried over -> read it back


def _clean(text: str) -> str:
    return re.sub(r"[’`]", "'", text.lower()).strip()


def find_period(text: str, today, default: PeriodKind = PeriodKind.this_month):
    """Returns (Period, named_explicitly)."""
    if DAY_WORD.search(text):
        day = today if "today" in text else today - timedelta(days=1)
        label = "today" if "today" in text else "yesterday"
        return Period(kind=PeriodKind.last_n_days, label=label, start=day, end=day), True
    if m := LAST_N_DAYS.search(text):
        return query.resolve_period(PeriodKind.last_n_days, today, days=int(m.group(1))), True
    for kind, pattern in PERIOD_PATTERNS:
        if pattern.search(text):
            return query.resolve_period(kind, today), True
    if m := NAMED_MONTH.search(text):
        return query.resolve_period(PeriodKind.named_month, today, m.group(0)), True
    return query.resolve_period(default, today), False


def find_subject(text: str, vocab: Vocabulary) -> tuple[Subject, bool]:
    """Returns (Subject, found). Tries the prepositional phrase first, then the whole text."""
    for phrase in SUBJECT_PHRASE.findall(text):
        if subject := vocab.resolve(phrase):
            return subject, True
    if subject := vocab.resolve(text):
        return subject, True
    return Subject(), False


def find_metric(text: str) -> Metric | None:
    for metric, pattern in METRIC_PATTERNS:
        if pattern.search(text):
            # "what do I spend on subscriptions?" asks for a total, not a list, even
            # though it names a category whose name is also a metric cue. "What are my
            # recurring charges?" is still a list.
            if metric == Metric.list_recurring and SPEND_AMOUNT.search(text):
                continue
            return metric
    return None


def route(text: str, vocab: Vocabulary | None = None, today=None) -> Routed:
    """Fast, deterministic routing. Returns Intent.unknown when the parser should try."""
    q = _clean(text)

    if REPLAY.search(q):
        return Routed(Intent.replay)
    if IDENTITY.search(q):
        return Routed(Intent.identity)
    # Opinions and predictions are advice however they are phrased; other advice patterns
    # give way when the question is really asking for a figure.
    if STRONG_ADVICE.search(q) or (ADVICE.search(q) and not FACTUAL.search(q)):
        return Routed(Intent.advice_refused)
    if HELP.search(q):
        return Routed(Intent.help)
    if OUT_OF_SCOPE.search(q):
        return Routed(Intent.unsupported)

    if vocab is None or today is None:
        return Routed(Intent.unknown)

    period, period_named = find_period(q, today)
    subject, has_subject = find_subject(q, vocab)
    metric = find_metric(q)

    # Hero intents: only when the question is not scoped to a subject.
    if not has_subject and metric is None:
        if ANOMALIES.search(q):
            return Routed(Intent.anomalies)
        if COMPARE.search(q):
            return Routed(Intent.compare_last_month)
        if WHERE.search(q):
            return Routed(Intent.where_money_went)
        if SUMMARY.search(q):
            return Routed(Intent.month_summary)

    # "how much did I spend in July?" — a figure is asked for and the scope is clear.
    # A resolved subject on its own is enough: "anything from Amazon lately?"
    if metric is None and (has_subject or (FACTUAL.search(q) and period_named)):
        metric = Metric.total_out
    if metric is None:
        # A subject was named but is not in this ledger ("how much on pets?"): say so,
        # rather than sending it to the parser to be guessed at.
        if FACTUAL.search(q) and SUBJECT_PHRASE.search(q):
            return Routed(Intent.unsupported)
        return Routed(Intent.unknown)

    plan = QueryPlan(metric=metric, subject=subject, period=period)
    return Routed(Intent.lookup, plan=plan, inferred=not period_named)


def is_followup(text: str) -> bool:
    return bool(FOLLOWUP.match(_clean(text)))


def merge_followup(text: str, previous: QueryPlan, vocab: Vocabulary, today) -> QueryPlan | None:
    """"what about last month?" / "and groceries?" -> previous plan with one slot replaced."""
    q = FOLLOWUP.sub("", _clean(text)).strip(" ?.!")
    if not q:
        return None
    period, period_named = find_period(q, today, default=previous.period.kind)
    subject, has_subject = find_subject(q, vocab)
    metric = find_metric(q) or previous.metric
    if not (period_named or has_subject):
        return None
    return QueryPlan(
        metric=metric,
        subject=subject if has_subject else previous.subject,
        period=period if period_named else previous.period,
        limit=previous.limit,
        source=PlanSource.followup,
    )
