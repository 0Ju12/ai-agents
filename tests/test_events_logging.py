"""검증 4.3 — 이벤트 발행은 구독자에 의존하지 않고, 로깅 Agent 는 세션별로 그대로 저장."""

from backend.events.bus import EventBus
from backend.logging_agent.agent import LoggingAgent
from backend.store.db import Store


def test_publish_survives_broken_subscriber():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("logger down")))
    bus.subscribe(seen.append)
    ev = bus.emit("s1", "node_start", "plan")
    assert ev.seq == 1 and seen == [ev]


def test_logging_agent_stores_by_session_in_order():
    bus, store = EventBus(), Store(":memory:")
    LoggingAgent(store).attach(bus)
    bus.emit("a", "node_start", "analyze_intent")
    bus.emit("b", "node_start", "analyze_intent")
    bus.emit("a", "llm_decision", "analyze_intent", decision="plan_trip", reason="여행 표현")
    logs = store.get_session_logs("a")
    assert [l["type"] for l in logs] == ["node_start", "llm_decision"]
    assert logs[1]["payload"]["reason"] == "여행 표현"
    assert {s["session_id"] for s in store.list_sessions()} == {"a", "b"}
    assert store.delete_session_logs("a") == 2 and store.get_session_logs("a") == []


def test_log_store_has_no_update():
    assert not any(name.startswith("update_log") or name == "update_session_logs" for name in dir(Store))


def test_plan_overlap_is_reported_but_saved():
    store = Store(":memory:")
    store.create_plan("기존 일정", "2026-11-21", "14:00", "16:00")
    plan, overlaps = store.create_plan("경주 답사", "2026-11-21", "08:00", "20:40")
    assert plan["id"] == 2 and [o["title"] for o in overlaps] == ["기존 일정"]
    _, none = store.create_plan("다른 날", "2026-11-22", "08:00", "20:40")
    assert none == []
