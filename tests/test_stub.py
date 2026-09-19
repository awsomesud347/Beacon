import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app

SECRET = "test-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STUB_MODE", "1")
    monkeypatch.setenv("LLM_PROXY_SECRET", SECRET)
    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def test_query_routes_to_examples(client):
    unusual = client.post("/api/query", json={"text": "What's unusual?"}).json()
    assert unusual["intent"] == "anomalies"
    assert "$47" in unusual["narration"]
    assert client.post("/api/query", json={"text": "Should I invest?"}).json()["intent"] == (
        "advice_refused"
    )
    assert client.get("/api/turns/latest").json()["turn_id"] != unusual["turn_id"]


def test_proxy_streams_sentences(client):
    body = {"messages": [{"role": "user", "content": "what's unusual"}], "stream": True}
    headers = {"Authorization": f"Bearer {SECRET}"}
    r = client.post("/v1/chat/completions", json=body, headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text.count("chat.completion.chunk") == 3
    assert r.text.endswith("data: [DONE]\n\n")


def test_proxy_rejects_bad_secret(client):
    r = client.post("/v1/chat/completions", json={"messages": []}, headers={"Authorization": "x"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_dataset_and_voice(client):
    assert client.get("/api/dataset").json()["current_period"] == "September 2026"
    assert client.get("/api/voice/session").json()["agent_id"]
