import json

import pytest

from backend.contract import DatasetInfo, FactBundle, Turn, VoiceSession
from backend.contract_export import (
    CONTRACT_DIR,
    OPENAPI_PATH,
    SSE_EXAMPLE_PATH,
    render_openapi,
    render_sse_example,
)

EXAMPLES = {
    "fact_bundle_anomalies.json": FactBundle,
    "turn_anomalies.json": Turn,
    "turn_summary.json": Turn,
    "turn_refusal.json": Turn,
    "turn_unknown.json": Turn,
    "dataset_info.json": DatasetInfo,
    "voice_session.json": VoiceSession,
}

REGENERATE = "run scripts/contract.ps1 and commit the result"


def test_openapi_is_up_to_date():
    assert json.loads(OPENAPI_PATH.read_text()) == json.loads(render_openapi()), REGENERATE


def test_sse_example_is_up_to_date():
    assert SSE_EXAMPLE_PATH.read_text() == render_sse_example(), REGENERATE


@pytest.mark.parametrize("name,model", EXAMPLES.items())
def test_example_matches_contract(name, model):
    raw = json.loads((CONTRACT_DIR / "examples" / name).read_text())
    parsed = model.model_validate(raw)
    assert json.loads(parsed.model_dump_json()) == raw


def test_every_example_is_checked():
    on_disk = {p.name for p in (CONTRACT_DIR / "examples").glob("*.json")}
    assert on_disk == set(EXAMPLES)
