import json

import pytest
from fastapi.testclient import TestClient

from agentkit.main import create_app
from tests.conftest import ScriptedModel

H = {"X-Session-Id": "session-test-0001"}
OTHER = {"X-Session-Id": "session-test-0002"}


def sse(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def client(settings):
    model = ScriptedModel([[("calculator", {"expression": "0.175 * 2340"})], "409.5"] * 10)
    with TestClient(create_app(settings, model=model)) as c:
        yield c


def test_templates_and_tools_are_listed(client):
    agents = client.get("/api/agents", headers=H).json()
    assert {a["id"] for a in agents} >= {"research-assistant", "money-and-dates", "support-agent", "page-summariser"}
    assert all(a["template"] for a in agents)
    assert {t["name"] for t in client.get("/api/tools").json()} >= {"calculator", "wikipedia_search", "search_notes"}


def test_create_edit_delete_agent_is_private_to_the_session(client):
    created = client.post("/api/agents", json={"name": "Mine", "instructions": "x", "tools": ["calculator"]}, headers=H)
    assert created.status_code == 201
    agent_id = created.json()["id"]
    assert client.get(f"/api/agents/{agent_id}", headers=OTHER).status_code == 404
    updated = client.put(
        f"/api/agents/{agent_id}", json={"name": "Renamed", "tools": ["calculator", "date_math"]}, headers=H
    ).json()
    assert updated["name"] == "Renamed" and updated["tools"] == ["calculator", "date_math"]
    assert client.delete(f"/api/agents/{agent_id}", headers=OTHER).status_code == 404
    assert client.delete(f"/api/agents/{agent_id}", headers=H).status_code == 204


def test_templates_are_read_only(client):
    assert client.put("/api/agents/money-and-dates", json={"name": "Hacked"}, headers=H).status_code == 403
    assert client.delete("/api/agents/money-and-dates", headers=H).status_code == 404


def test_unknown_tool_is_rejected(client):
    r = client.post("/api/agents", json={"name": "Bad", "tools": ["shell"]}, headers=H)
    assert r.status_code == 422


def test_run_streams_trace_and_is_saved(client):
    response = client.post("/api/agents/money-and-dates/run", json={"input": "What is 17.5% of 2,340?"}, headers=H)
    events = sse(response)
    assert [e["type"] for e in events] == ["start", "model", "tool_call", "tool_result", "model", "answer", "done"]
    done = events[-1]
    assert done["answer"] == "409.5"
    run = client.get(f"/api/runs/{done['run_id']}", headers=H).json()
    assert run["status"] == "completed" and len(run["steps"]) == 6
    assert client.get(f"/api/runs/{done['run_id']}", headers=OTHER).status_code == 404
    assert client.get("/api/agents/money-and-dates/runs", headers=H).json()[0]["id"] == done["run_id"]


def test_run_without_model_returns_503(settings):
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/agents/money-and-dates/run", json={"input": "hi"}, headers=H).status_code == 503
        assert c.get("/api/config").json()["llm_ready"] is False


def test_rate_limit(settings):
    settings.runs_per_10min = 1
    with TestClient(create_app(settings, model=ScriptedModel(["a", "b"]))) as c:
        assert c.post("/api/agents/money-and-dates/run", json={"input": "hi"}, headers=H).status_code == 200
        assert c.post("/api/agents/money-and-dates/run", json={"input": "hi"}, headers=H).status_code == 429
