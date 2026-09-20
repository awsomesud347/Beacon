"""Question -> QueryPlan, using the language model as a *parser only*.

It chooses filters (metric, subject, period) from a fixed whitelist. It never returns a
figure, so the "the model cannot hallucinate a number" guarantee is untouched: the plan is
executed by pandas afterwards. Anything that fails validation — an invented category, a
metric we do not support, malformed JSON — becomes None, and the caller answers honestly
that it cannot help.
"""

import json
import logging
import re
from datetime import date

from pydantic import BaseModel, ValidationError

from backend.analysis import query
from backend.analysis.vocab import Vocabulary
from backend.contract import Metric, PeriodKind, PlanSource, QueryPlan, Subject, SubjectKind
from backend.narration.client import _THINK, _client

log = logging.getLogger("beacon.parser")
MAX_TOKENS = 200
TIMEOUT_S = 6.0
_JSON = re.compile(r"\{.*\}", re.S)


class RawPlan(BaseModel):
    """Exactly what the model is allowed to say."""

    metric: Metric
    subject_kind: SubjectKind = SubjectKind.all
    subject: str | None = None
    period_kind: PeriodKind = PeriodKind.this_month
    period_value: str | None = None  # month name for named_month, day count for last_n_days
    limit: int | None = None


SYSTEM = """You convert a question about someone's own spending into a JSON query plan.
You never answer the question and never write any number from the data.

Reply with JSON only, no prose, using exactly these fields:
{{"metric": ..., "subject_kind": ..., "subject": ..., "period_kind": ..., "period_value": ..., \
"limit": ...}}

metric (pick one):
  total_out       how much was spent
  total_in        how much came in (income, pay, deposits)
  net             what is left: money in versus money out, saving
  count           how many times / how often
  average         typical or average amount
  largest         biggest or most expensive single purchase
  smallest        smallest single purchase
  list_recurring  which subscriptions or regular charges exist
  top_merchants   which shops or merchants are biggest
  top_categories  which categories are biggest
  trend           whether something is going up or down over time

subject_kind: all, category, or merchant.
subject: MUST be copied exactly from these lists, or null.
  categories: {categories}
  merchants: {merchants}
Everyday words map onto those categories: eating out / takeout / restaurants -> dining,
gas / fuel / rides -> transport, food shopping -> groceries, streaming / memberships ->
subscriptions, bills / power / water / internet -> utilities, pay / salary -> income.
If the question names something that is not in either list, reply {{"metric": "unsupported"}}.

period_kind: this_month, last_month, named_month, last_n_days, this_week, last_week,
this_year, all_time. Use this_month when no time is mentioned.
period_value: for named_month the month name ("July"); for last_n_days the number of days
("30"); otherwise null.
limit: how many items for list metrics, else null.

Today is {today}.
{previous}
If the question is not about this person's own transactions, or needs something not in the
list above, reply exactly {{"metric": "unsupported"}}."""


def _messages(question: str, vocab: Vocabulary, previous: QueryPlan | None, today: date):
    context = ""
    if previous:
        context = (f"The previous question was about {query.understood_phrase(previous)} "
                   f"(metric {previous.metric.value}). If this question only changes part of "
                   f"it, keep the rest.")
    system = SYSTEM.format(
        categories=", ".join(vocab.categories) or "none",
        merchants=", ".join(vocab.top_merchants(25)) or "none",
        today=today.isoformat(),
        previous=context,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def _to_plan(raw: RawPlan, vocab: Vocabulary, today: date) -> QueryPlan | None:
    subject = Subject()
    if raw.subject:
        resolved = vocab.validate(Subject(kind=raw.subject_kind, value=raw.subject))
        if resolved is None:
            log.info("parser named a subject that is not in the data: %r", raw.subject)
            return None
        subject = resolved
    days = int(raw.period_value) if (raw.period_value or "").isdigit() else None
    period = query.resolve_period(raw.period_kind, today, value=raw.period_value, days=days)
    return QueryPlan(metric=raw.metric, subject=subject, period=period, limit=raw.limit,
                     source=PlanSource.model)


def parse(question: str, vocab: Vocabulary, previous: QueryPlan | None,
          today: date) -> QueryPlan | None:
    """Returns a validated plan, or None to answer honestly that we cannot help."""
    configured = _client()
    if configured is None:
        return None
    client, model = configured
    try:
        response = client.chat.completions.create(
            model=model,
            messages=_messages(question, vocab, previous, today),
            temperature=0,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_S,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        # Not the narration cleaner: it strips "_" as markdown, which would turn
        # "total_out" into "totalout" and fail every parse.
        text = _THINK.sub("", response.choices[0].message.content or "")
    except Exception:
        log.exception("parser call failed")
        return None

    match = _JSON.search(text)
    if not match:
        log.info("parser returned no JSON: %r", text[:200])
        return None
    try:
        raw = RawPlan.model_validate_json(match.group(0))
    except (ValidationError, json.JSONDecodeError):
        log.info("parser returned an unusable plan: %r", match.group(0)[:200])
        return None
    return _to_plan(raw, vocab, today)
