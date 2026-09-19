"""End-to-end over HTTP with the real engine and the template narrator (no network)."""

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
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_hero_query(client):
    turn = client.post("/api/query", json={"text": "What's unusual?"}).json()
    assert turn["intent"] == "anomalies"
    assert "$47" in turn["narration"]
    assert turn["fact_bundle"]["anomalies"][0]["type"] == "new_recurring"
    assert turn["guard"]["passed"] is True
    assert "account" not in json.dumps(turn["fact_bundle"])


def test_refusal_and_replay(client):
    refusal = client.post("/api/query", json={"text": "Should I invest?"}).json()
    assert refusal["narration_source"] == "refusal"
    assert refusal["fact_bundle"] is None
    replay = client.post("/api/query", json={"text": "repeat that"}).json()
    assert replay["narration"] == refusal["narration"]
    assert replay["narration_source"] == "replay"


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
    turn = client.post("/api/query", json={"text": "What's unusual?"}).json()
    assert "$47" in turn["narration"]
    assert client.post("/api/dataset/reset").json()["source"] == "fixture"


def test_upload_rejects_bad_csv(client):
    r = client.post("/api/dataset/upload", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 422
    assert r.json()["code"] == "csv_invalid"


def test_voice_proxy_matches_text_answer(client):
    text = client.post("/api/query", json={"text": "What's unusual?"}).json()["narration"]
    body = {"messages": [{"role": "system", "content": "x"},
                         {"role": "user", "content": "anything unusual?"}], "stream": False}
    r = client.post("/v1/chat/completions", json=body,
                    headers={"Authorization": f"Bearer {SECRET}"})
    assert r.json()["choices"][0]["message"]["content"] == text
    assert client.get("/api/turns/latest").json()["channel"] == "voice"
