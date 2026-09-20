"""Question -> decision, by the model. No pattern matching.

One call decides what kind of question this is and, for a data question, which filters to
apply. It never returns a figure: pandas computes every number afterwards and the guard
checks whatever is spoken. The model can therefore be wrong about *what* was asked — which
the read-back makes audible — but it cannot be wrong about a number.

Coherence over cleverness: if the model returns something unusable, we fall back to an
overview answer rather than a dead end.
"""

import json
import logging
import re
from datetime import date

from pydantic import BaseModel, ValidationError

from backend.analysis import query
from backend.analysis.vocab import Vocabulary
from backend.contract import (
    Intent,
    Metric,
    PeriodKind,
    PlanSource,
    QueryPlan,
    Subject,
    SubjectKind,
)
from backend.narration.client import _THINK, _client

log = logging.getLogger("beacon.planner")
MAX_TOKENS = 220
TIMEOUT_S = 8.0
_JSON = re.compile(r"\{.*\}", re.S)

KINDS = {
    "data": Intent.lookup,
    "advice": Intent.advice_refused,
    "identity": Intent.identity,
    "help": Intent.help,
    "repeat": Intent.replay,
    "unsupported": Intent.unsupported,
}


class Decision(BaseModel):
    """Exactly what the model is allowed to decide."""

    kind: str
    metric: Metric = Metric.total_out
    subject_kind: SubjectKind = SubjectKind.all
    subject: str | None = None
    period_kind: PeriodKind = PeriodKind.this_month
    period_value: str | None = None
    limit: int | None = None
    # The thing the question named, copied verbatim. If this is set but `subject` is null,
    # the question was about something this ledger does not contain — say so rather than
    # quietly answering about everything.
    mentions: str | None = None


SYSTEM = """You are the router for a tool that answers questions about one person's own \
spending, out loud, for someone who cannot see the screen. You decide what the question is \
asking for. You never answer it and never write any number.

Reply with JSON only:
{{"kind": ..., "metric": ..., "subject_kind": ..., "subject": ..., "period_kind": ..., \
"period_value": ..., "limit": ...}}

kind:
  data         a question about their money that these figures can answer
  advice       asks what they should do, whether to buy something, or predicts the future
  identity     asks what or who this tool is, or whether the data is real
  help         asks what it can do or what they can ask
  repeat       asks to hear the last answer again
  unsupported  about money but not answerable here (bank balance, transfers, other accounts),
               or not about their money at all

For kind "data", also choose:
metric:
  total_out       how much was spent            total_in    money coming in, pay, deposits
  net             what is left, saving          count       how many times, how often
  average         typical amount                largest     biggest single purchase
  smallest        smallest single purchase      trend       going up or down over time
  list_recurring  which subscriptions or regular charges exist
  top_merchants   which shops are biggest       top_categories  which categories are biggest
  summary         how the month is going overall, or where the money went
  anomalies       what is unusual, surprising, wrong, or stands out

subject_kind: all, category, or merchant. Use "all" for the whole month.
subject: copied EXACTLY from these lists, or null.
  categories: {categories}
  merchants: {merchants}
Everyday words map to categories: eating out, takeout, restaurants -> dining; gas, fuel, \
rides -> transport; food shopping -> groceries; streaming, memberships -> subscriptions; \
bills, power, water, internet -> utilities; pay, salary -> income.
If the question names something that is in neither list, set subject to null and kind to \
"unsupported".

period_kind: this_month, last_month, named_month, last_n_days, this_week, last_week, \
this_year, all_time. Use this_month unless another time is mentioned.
period_value: month name for named_month ("July"); number of days for last_n_days ("30"); \
otherwise null.
limit: how many items for list metrics, else null.
mentions: if the question names a specific thing to spend money on (a category, a shop, a
bill), copy that word from the question here, even when you set subject to null because it
is not in the lists. Otherwise null.

Today is {today}. The data covers {coverage}.
{history}
Rules that decide the close calls:
- "how much", "what did I spend", "what's my X" -> total_out, even when X is also the name
  of a metric ("what do I spend on subscriptions" is total_out for the subscriptions
  category, not list_recurring).
- Prefer a category over a merchant when the word names one ("coffee" is the category, not
  the shop "Blue Bottle Coffee").
- A question about one named shop is total_out for that merchant, not top_merchants
  ("did Netflix charge me", "anything from Amazon").
- Anything about balances, transfers, other accounts, or the world outside these
  transactions is "unsupported", never "data".

Examples:
"what's unusual" -> {{"kind":"data","metric":"anomalies","subject_kind":"all","subject":null,\
"period_kind":"this_month","period_value":null,"limit":null}}
"anything I should know about?" -> {{"kind":"data","metric":"anomalies",\
"subject_kind":"all","subject":null,"period_kind":"this_month","period_value":null,\
"limit":null}}
"how am I doing this month" -> {{"kind":"data","metric":"summary","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}
"how does this compare to last month" -> {{"kind":"data","metric":"summary",\
"subject_kind":"all","subject":null,"period_kind":"this_month","period_value":null,\
"limit":null}}
"where did my money go" -> {{"kind":"data","metric":"top_categories","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":5}}
"how much on eating out in July" -> {{"kind":"data","metric":"total_out",\
"subject_kind":"category","subject":"dining","period_kind":"named_month",\
"period_value":"July","limit":null}}
"did Netflix charge me this month" -> {{"kind":"data","metric":"total_out",\
"subject_kind":"merchant","subject":"Netflix","period_kind":"this_month",\
"period_value":null,"limit":null}}
"what's my coffee habit costing me" -> {{"kind":"data","metric":"total_out",\
"subject_kind":"category","subject":"coffee","period_kind":"this_month",\
"period_value":null,"limit":null}}
"what did I spend yesterday" -> {{"kind":"data","metric":"total_out","subject_kind":"all",\
"subject":null,"period_kind":"last_n_days","period_value":"1","limit":null}}
"and last month?" (after a question about groceries) -> {{"kind":"data",\
"metric":"total_out","subject_kind":"category","subject":"groceries",\
"period_kind":"last_month","period_value":null,"limit":null}}
"what's my bank balance" -> {{"kind":"unsupported","metric":"total_out",\
"subject_kind":"all","subject":null,"period_kind":"this_month","period_value":null,\
"limit":null}}
"do you think I spend too much" -> {{"kind":"advice","metric":"total_out",\
"subject_kind":"all","subject":null,"period_kind":"this_month","period_value":null,\
"limit":null}}
"who are you" -> {{"kind":"identity","metric":"total_out","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}
"is this real data" -> {{"kind":"identity","metric":"total_out","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}
"what can I ask you" -> {{"kind":"help","metric":"total_out","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}
"say that again" -> {{"kind":"repeat","metric":"total_out","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}
"am I still paying Planet Fitness" -> {{"kind":"data","metric":"total_out",\
"subject_kind":"merchant","subject":"Planet Fitness","period_kind":"this_month",\
"period_value":null,"limit":null}}
"what came in versus what went out" -> {{"kind":"data","metric":"net","subject_kind":"all",\
"subject":null,"period_kind":"this_month","period_value":null,"limit":null}}"""


def _history_block(history: list[tuple[str, str]]) -> str:
    if not history:
        return ""
    lines = "\n".join(f'  they asked: "{q}" and you looked up: {summary}'
                      for q, summary in history)
    last = history[-1][1]
    return (f"Recent turns, oldest last:\n{lines}\n"
            f"IMPORTANT: the question you are routing now may be a short follow-up ('and "
            f"last month?', 'what about groceries?', 'and at Kroger?'). If it is, start "
            f"from the previous lookup ({last}) and change ONLY the part the new question "
            f"names — keep the metric, the subject and the period it does not mention.\n")


def _messages(question: str, vocab: Vocabulary, history: list[tuple[str, str]], today: date,
              coverage: str):
    system = SYSTEM.format(
        categories=", ".join(vocab.categories) or "none",
        merchants=", ".join(vocab.top_merchants(30)) or "none",
        today=today.isoformat(),
        coverage=coverage,
        history=_history_block(history),
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def _to_plan(decision: Decision, vocab: Vocabulary, today: date) -> QueryPlan | None:
    subject = Subject()
    if decision.subject:
        resolved = vocab.validate(Subject(kind=decision.subject_kind, value=decision.subject))
        if resolved is None:
            log.info("planner named something not in the ledger: %r", decision.subject)
            return None
        subject = resolved
    days = int(decision.period_value) if (decision.period_value or "").isdigit() else None
    period = query.resolve_period(decision.period_kind, today, value=decision.period_value,
                                  days=days)
    return QueryPlan(metric=decision.metric, subject=subject, period=period,
                     limit=decision.limit, source=PlanSource.model)


def decide(question: str, vocab: Vocabulary, history: list[tuple[str, str]], today: date,
           coverage: str) -> tuple[Intent, QueryPlan | None]:
    """(intent, plan). Returns (Intent.unknown, None) only when the model is unreachable."""
    configured = _client()
    if configured is None:
        return Intent.unknown, None
    client, model = configured
    try:
        response = client.chat.completions.create(
            model=model,
            messages=_messages(question, vocab, history, today, coverage),
            temperature=0,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_S,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = _THINK.sub("", response.choices[0].message.content or "")
    except Exception:
        log.exception("planner call failed")
        return Intent.unknown, None

    match = _JSON.search(raw)
    if not match:
        log.info("planner returned no JSON: %r", raw[:200])
        return Intent.unknown, None
    try:
        decision = Decision.model_validate_json(match.group(0))
    except (ValidationError, json.JSONDecodeError):
        log.info("planner returned an unusable decision: %r", match.group(0)[:200])
        return Intent.unknown, None

    intent = KINDS.get(decision.kind.lower().strip(), Intent.unsupported)
    if intent != Intent.lookup:
        return intent, None
    plan = _to_plan(decision, vocab, today)
    if plan is None:
        # It asked for something real-sounding that is not in this ledger.
        return Intent.unsupported, None
    # The question named something the ledger does not have ("how much on pets?").
    # Answering about everything instead would be answering a question nobody asked.
    if decision.mentions and not decision.subject and vocab.resolve(decision.mentions) is None:
        log.info("question named %r, which is not in this ledger", decision.mentions)
        return Intent.unsupported, None
    return Intent.lookup, plan
