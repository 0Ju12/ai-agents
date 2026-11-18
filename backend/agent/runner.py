"""대화 1회 실행 + 대화 맥락(F3010).

메모리에는 조건 요약만 남기고 Tool 원본 응답은 보관하지 않는다.
"""

from __future__ import annotations

import uuid

from backend.events.bus import Event, bus

from .graph import build_graph

_graph = None
_MEMORY: dict[str, dict] = {}  # session_id → 직전 조건 (TODO: SQLite 로 옮겨 재시작 후에도 유지)


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run(message: str, session_id: str | None = None) -> dict:
    sid = session_id or uuid.uuid4().hex[:12]
    steps: list[dict] = []

    def collect(e: Event) -> None:
        if e.session_id == sid:
            steps.append(e.to_dict())

    bus.subscribe(collect)
    try:
        state = _get_graph().invoke({"session_id": sid, "message": message, "conditions": dict(_MEMORY.get(sid, {})),
                                     "results": {}, "replan_count": 0})
    finally:
        bus.unsubscribe(collect)
    _MEMORY[sid] = state.get("conditions") or {}
    return {"session_id": sid, "answer": state.get("answer", ""), "intent": state.get("intent"),
            "replans": state.get("replan_count", 0), "steps": steps}
