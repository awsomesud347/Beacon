"""End-to-end over HTTP with the real engine and no model reachable.

With the planner unreachable every question falls back to an overview answer rather than a
dead end — that is the deliberate behaviour, because a demo that says nothing is worse than
one that says something true but general. Model-driven routing is measured separately by
scripts/eval_parser.py against a live model.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import state
from backend.config import get_settings
from backend.main import create_app
from data.generate import FIXTURES

SECRET = "test-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STUB_MODE", "0")
    monkeypatch.setenv("NARRATOR", "template")
    monkeypatch.setenv("PRECOMPUTE", "0")
    monkeypatch.setenv("LLM_PROXY_SECRET", SECRET)
    monkeypatch.setenv("DATASET_PATH", str(FIXTURES / "demo_persona.csv"))
    get_settings.cache_clear()
    state.state.last_narration = None
    state.state.history.clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_every_question_gets_a_true_answer_even_without_a_model(client):
    turn = client.post("/api/query", json={"text": "What's unusual?"}).json()
    assert turn["intent"] == "lookup"
    assert turn["fact_bundle"]["lookup"]["total"] > 0
    assert "September 2026" in turn["narration"]
    assert turn["guard"]["passed"] is True


def test_the_model_never_receives_transactions(client):
    turn = client.post("/api/query", json={"text": "how am I doing?"}).json()
    payload = json.dumps(turn["fact_bundle"])
    assert "account" not in payload
    assert "checking" not in payload and "credit" not in payload
    assert "KROGER #412" not in payload  # raw merchant strings never leave


def test_overview_ships_with_the_answer(client):
    overview = client.post("/api/query", json={"text": "how am I doing?"}).json()[
        "fact_bundle"]["overview"]
    assert overview["current_period"] == "September 2026"
    assert len(overview["months"]) == 6
    assert overview["categories_this_period"][0]["name"] == "rent"
    assert any(r["name"] == "Netflix" for r in overview["recurring"])


def test_advice_is_refused_without_asking_the_model(client):
    refusal = client.post("/api/query", json={"text": "Should I cancel Netflix?"}).json()
    assert refusal["intent"] == "advice_refused"
    assert refusal["narration_source"] == "refusal"
    assert refusal["fact_bundle"] is None


def test_replay_repeats_the_last_answer(client):
    first = client.post("/api/query", json={"text": "how am I doing?"}).json()
    replay = client.post("/api/query", json={"text": "say that again"}).json()
    # No model, so "say that again" cannot be routed to replay; it must still answer.
    assert replay["narration"]
    assert first["narration"]


def test_health_reports_dataset(client):
    health = client.get("/api/health").json()
    assert health["dataset"]["current_period"] == "September 2026"
    assert health["narrator"] == "template"


def test_upload_and_reset(client):
    messy = (FIXTURES / "messy_bank_export.csv").read_bytes()
    info = client.post("/api/dataset/upload",
                       files={"file": ("export.csv", messy, "text/csv")}).json()
    assert info["source"] == "upload"
    assert info["name"] == "export.csv"
    turn = client.post("/api/query", json={"text": "how am I doing?"}).json()
    assert turn["fact_bundle"]["lookup"]["total"] > 0
    assert client.post("/api/dataset/reset").json()["source"] == "fixture"


def test_upload_rejects_bad_csv(client):
    r = client.post("/api/dataset/upload", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 422
    assert r.json()["code"] == "csv_invalid"


def test_voice_proxy_matches_text_answer(client):
    text = client.post("/api/query", json={"text": "how am I doing?"}).json()["narration"]
    body = {"messages": [{"role": "system", "content": "x"},
                         {"role": "user", "content": "how am I doing?"}], "stream": False}
    r = client.post("/v1/chat/completions", json=body,
                    headers={"Authorization": f"Bearer {SECRET}"})
    assert r.json()["choices"][0]["message"]["content"] == text
    assert client.get("/api/turns/latest").json()["channel"] == "voice"
