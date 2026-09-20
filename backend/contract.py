"""The shared seam between backend and frontend.

Every API shape lives here. After editing, run scripts/contract.ps1 to regenerate
contract/openapi.json and frontend/src/api/contract.gen.ts. Breaking changes bump
CONTRACT_VERSION and go in their own `contract:` commit.

Number conventions (the narration guard depends on these):
- money is a positive magnitude rounded to 2 decimals
- percentages are rounded to 1 decimal
- no dates in a FactBundle other than `period`
- nothing internal (severity, z-scores, transaction ids, account ids) is ever in a FactBundle
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "2"


# --- Enums -------------------------------------------------------------------


class Intent(StrEnum):
    anomalies = "anomalies"
    month_summary = "month_summary"
    where_money_went = "where_money_went"
    compare_last_month = "compare_last_month"
    lookup = "lookup"  # any scoped question; the QueryPlan says what was asked
    replay = "replay"
    advice_refused = "advice_refused"
    identity = "identity"  # "who are you", "is this real data"
    help = "help"
    unsupported = "unsupported"  # understood, but outside what we can answer
    unknown = "unknown"  # not understood at all


class Metric(StrEnum):
    total_out = "total_out"
    total_in = "total_in"
    net = "net"
    count = "count"
    average = "average"
    largest = "largest"
    smallest = "smallest"
    list_recurring = "list_recurring"
    top_merchants = "top_merchants"
    top_categories = "top_categories"
    trend = "trend"


class SubjectKind(StrEnum):
    all = "all"
    category = "category"
    merchant = "merchant"


class PeriodKind(StrEnum):
    this_month = "this_month"
    last_month = "last_month"
    named_month = "named_month"
    last_n_days = "last_n_days"
    this_week = "this_week"
    last_week = "last_week"
    this_year = "this_year"
    all_time = "all_time"


class PlanSource(StrEnum):
    pattern = "pattern"  # deterministic router; no model involved
    model = "model"  # parsed by the language model, then validated
    followup = "followup"  # carried over from the previous question


class Verdict(StrEnum):
    normal = "normal"
    normal_with_exception = "normal_with_exception"
    unusual = "unusual"
    no_data = "no_data"


class AnomalyType(StrEnum):
    new_recurring = "new_recurring"
    duplicate_charge = "duplicate_charge"
    amount_drift = "amount_drift"
    missing_recurring = "missing_recurring"
    category_outlier = "category_outlier"
    large_transaction = "large_transaction"


class NarrationSource(StrEnum):
    model = "model"
    template = "template"
    refusal = "refusal"
    replay = "replay"
    cache = "cache"


class Channel(StrEnum):
    text = "text"
    voice = "voice"


class SseEvent(StrEnum):
    turn = "turn"
    dataset = "dataset"
    ping = "ping"


class ErrorCode(StrEnum):
    invalid_request = "invalid_request"
    csv_invalid = "csv_invalid"
    dataset_empty = "dataset_empty"
    narration_failed = "narration_failed"
    unauthorized = "unauthorized"
    not_found = "not_found"
    not_implemented = "not_implemented"


# --- FactBundle: the only thing the language model ever sees -----------------


class Anomaly(BaseModel):
    """Flat shape; which optional fields are set depends on `type`.

    new_recurring      merchants, category, count, total
    duplicate_charge   merchants, count, amount, total
    amount_drift       merchants, amount, previous_amount, change_pct
    missing_recurring  merchants, amount
    category_outlier   category, amount, typical_amount, change_pct
    large_transaction  merchants, category, amount
    """

    type: AnomalyType
    merchants: list[str] = Field(default_factory=list)
    category: str | None = None
    count: int | None = None
    total: float | None = None
    amount: float | None = None
    previous_amount: float | None = None
    change_pct: float | None = None
    typical_amount: float | None = None


class CategoryAmount(BaseModel):
    name: str
    amount: float
    delta_pct: float | None = None


class MonthSummary(BaseModel):
    total_in: float
    total_out: float
    net: float
    top_categories: list[CategoryAmount] = Field(default_factory=list, max_length=5)


class Comparison(BaseModel):
    current_total_out: float
    prior_total_out: float
    delta_pct: float
    biggest_increase: CategoryAmount | None = None
    biggest_decrease: CategoryAmount | None = None


class Context(BaseModel):
    month_total_out: float
    prior_month_total_out: float
    delta_pct: float


# --- Query plan: what the model is allowed to decide (filters, never figures) ----


class Subject(BaseModel):
    """What the question is about. `value` is always a real category or merchant in the
    loaded ledger — the parser cannot invent one."""

    kind: SubjectKind = SubjectKind.all
    value: str | None = None


class Period(BaseModel):
    kind: PeriodKind = PeriodKind.this_month
    label: str = Field(examples=["September 2026", "the last 30 days"])
    start: date
    end: date


class QueryPlan(BaseModel):
    """The parsed question. Executed deterministically; no number originates here."""

    metric: Metric
    subject: Subject = Field(default_factory=Subject)
    period: Period
    limit: int | None = Field(default=None, ge=1, le=10)
    source: PlanSource = PlanSource.pattern


class MerchantAmount(BaseModel):
    merchant: str
    amount: float


class Lookup(BaseModel):
    """Result of executing a QueryPlan. Every figure computed by pandas."""

    subject_label: str = Field(examples=["groceries", "Kroger", "everything"])
    period_label: str
    total: float
    count: int
    average: float | None = None
    prior_total: float | None = None
    delta_pct: float | None = None
    largest: MerchantAmount | None = None
    items: list[CategoryAmount] = Field(default_factory=list, max_length=10)
    empty: bool = False


class FactBundle(BaseModel):
    contract_version: str = CONTRACT_VERSION
    query_type: Intent
    period: str = Field(examples=["September 2026"])
    verdict: Verdict
    anomalies: list[Anomaly] = Field(default_factory=list, max_length=3)
    summary: MonthSummary | None = None
    comparison: Comparison | None = None
    context: Context
    plan: QueryPlan | None = None
    lookup: Lookup | None = None
    understood: str | None = Field(
        default=None,
        description="Read-back of how the question was understood, set only when something "
                    "was inferred or carried over from the previous question.",
        examples=["groceries in July"],
    )


# --- Turn: every answer, text or voice ---------------------------------------


class GuardResult(BaseModel):
    passed: bool
    attempts: int
    rejected_tokens: list[str] = Field(default_factory=list)


class Latency(BaseModel):
    analysis: int
    narration: int
    total: int


class Turn(BaseModel):
    turn_id: str
    created_at: datetime
    channel: Channel
    query_text: str
    intent: Intent
    narration: str
    narration_source: NarrationSource
    fact_bundle: FactBundle | None = None
    guard: GuardResult
    latency_ms: Latency
    audio_url: str | None = None


# --- REST request / response bodies ------------------------------------------


class QueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    channel: Channel = Channel.text
    discreet: bool = False


class DatasetInfo(BaseModel):
    source: Literal["fixture", "upload"]
    name: str
    row_count: int
    date_min: date
    date_max: date
    current_period: str


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    contract_version: str = CONTRACT_VERSION
    narrator: Literal["cloud", "local", "template"]
    demo_mode: bool
    stub_mode: bool
    dataset: DatasetInfo | None = None


class VoiceSession(BaseModel):
    agent_id: str
    signed_url: str | None = None
    conversation_token: str | None = None


class ApiError(BaseModel):
    code: ErrorCode
    message: str
    details: list[str] = Field(default_factory=list)


# --- OpenAI-compatible custom-LLM endpoint (called by the ElevenLabs agent) ---


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[dict] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    user_id: str | None = None
