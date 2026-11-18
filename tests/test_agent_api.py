"""검증 4.2·4.5 — 그래프 구조, 분기, 재계획 상한, API 경로."""

import pytest
from fastapi.testclient import TestClient

from backend.agent import nodes, runner
from backend.agent.graph import build_graph
from backend.api import deps
from backend.api.main import app
from backend.config import MAX_REPLAN
from backend.events.bus import bus
from backend.logging_agent.agent import LoggingAgent
from backend.store.db import Store
from backend.tools.base import Err, fail


@pytest.fixture
def client(monkeypatch):
    store = Store(":memory:")
    agent = LoggingAgent(store)
    bus.subscribe(agent.handle)
    app.dependency_overrides[deps.get_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()
    bus.unsubscribe(agent.handle)


def test_graph_nodes():
    names = set(build_graph().get_graph().nodes)
    assert {"analyze_intent", "extract_conditions", "plan", "execute", "judge", "replan", "respond", "ask_back"} <= names


def test_chitchat_skips_plan_and_tools():
    out = runner.run("고속버스 우등이랑 일반은 뭐가 달라?")
    assert out["intent"] == "chitchat"
    names = [s["name"] for s in out["steps"] if s["type"] == "node_start"]
    assert "plan" not in names and not any(s["type"] == "tool_call" for s in out["steps"])


def test_missing_conditions_ask_back_before_tools():
    out = runner.run("토요일에 경주 당일 여행 일정 짜 줘")
    assert "출발지" in out["answer"] and not any(s["type"] == "tool_call" for s in out["steps"])


def test_replan_stops_at_limit(monkeypatch):
    monkeypatch.setattr(nodes.registry, "run", lambda name, **kw: {**fail(Err.UPSTREAM_ERROR, "일시 오류"), "meta": {"tool": name, "elapsed_ms": 0}})
    out = runner.run("토요일 서울에서 KTX로 경주 당일 여행 가고 싶어")
    assert out["replans"] == MAX_REPLAN
    assert sum(s["type"] == "replan" for s in out["steps"]) == MAX_REPLAN
    assert "조건을 조정" in out["answer"]


def test_non_retryable_failure_does_not_replan():
    out = runner.run("토요일 서울에서 KTX로 경주 당일 여행 가고 싶어")  # 키 없음 → INVALID_KEY
    assert out["replans"] == 0 and "인증키" in out["answer"]


def test_api_plans_crud_and_overlap(client):
    c, _ = client
    body = {"title": "경주 답사", "trip_date": "2026-11-21", "start_time": "08:00", "end_time": "20:40"}
    first = c.post("/api/plans", json=body).json()
    second = c.post("/api/plans", json={**body, "title": "겹치는 일정", "start_time": "14:00", "end_time": "15:00"}).json()
    assert first["overlaps"] == [] and second["overlaps"][0]["title"] == "경주 답사"
    pid = first["plan"]["id"]
    assert c.patch(f"/api/plans/{pid}", json={"end_time": "13:00"}).json()["plan"]["end_time"] == "13:00"
    assert c.delete(f"/api/plans/{pid}").status_code == 204
    assert c.get(f"/api/plans/{pid}").status_code == 404


def test_api_chat_logs_and_no_log_update(client):
    c, store = client
    out = c.post("/api/chat", json={"message": "안녕하세요"}).json()
    sid = out["session_id"]
    assert c.get(f"/api/logs/{sid}").status_code == 200
    assert any(s["session_id"] == sid for s in c.get("/api/logs").json())
    assert c.put(f"/api/logs/{sid}", json={}).status_code == 405  # 수정 API 없음 (F3014)
    assert c.patch(f"/api/logs/{sid}", json={}).status_code == 405
    assert c.delete(f"/api/logs/{sid}").status_code == 204


def test_status_does_not_leak_keys(client):
    c, _ = client
    keys = c.get("/api/status").json()["keys"]
    assert set(keys) >= {"data_go_kr", "kakao_rest", "youtube", "openai"} and all(v is False for v in keys.values())
