"""로깅 서브 Agent (F3013).

이벤트를 구독해 받는 즉시 세션 단위 실행 로그에 발생 순서대로 덧붙인다.
수집과 저장에는 LLM 을 쓰지 않고, 이벤트를 요약·가공하지 않고 그대로 남긴다.
저장에 실패해도 대화는 정상 동작한다 (버스가 예외를 삼킴).
"""

from __future__ import annotations

from backend.events.bus import Event, EventBus
from backend.store.db import Store


class LoggingAgent:
    def __init__(self, store: Store):
        self.store = store

    def handle(self, event: Event) -> None:
        self.store.append_log(event.session_id, event.seq, event.type, event.name, event.payload, event.ts)

    def attach(self, bus: EventBus) -> "LoggingAgent":
        bus.subscribe(self.handle)
        return self


def assess(events, replan_limit):
    planned = set()
    called = set()
    warnings = []
    previous_failed_tool = None
    evidence = False
    n = 0
    for e in events:
        kind = e["type"]
        p = e["payload"]
        if kind == "plan":
            planned.update(p.get("tools", []))
            evidence = True
        elif kind == "tool_call":
            key = (e["name"], p.get("argument", ""))
            if e["name"] not in planned:
                warnings.append("계획 밖 호출 · " + e["name"])
            if key in called:
                warnings.append("같은 입력 반복 · " + e["name"])
            called.add(key)
            evidence = True
        elif kind == "tool_result":
            failed_tool = e["name"] if p.get("ok") is False else None
            if failed_tool and failed_tool == previous_failed_tool:
                warning = "도구 연속 실패 · " + failed_tool
                if warning not in warnings:
                    warnings.append(warning)
            previous_failed_tool = failed_tool
            evidence = True
        elif kind == "replan":
            n += 1
            evidence = True
    if n >= replan_limit:
        warnings.append("재계획 상한 도달")
    return {
        "status": "이상" if warnings else "정상" if evidence else "판정 불가",
        "warnings": warnings,
        "replans": n,
    }
