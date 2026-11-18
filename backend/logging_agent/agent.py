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
