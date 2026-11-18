"""실행 이벤트 발행 (F3012).

발행하는 쪽(메인 Agent)은 누가 구독하는지 모른다. 구독자(로깅 Agent)가 실패하거나
아예 없어도 메인 Agent 는 정상 동작해야 하므로, 구독자 예외는 여기서 삼킨다.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

EventType = Literal["node_start", "node_end", "tool_call", "tool_result", "llm_decision", "replan", "error"]


@dataclass
class Event:
    session_id: str
    type: EventType
    name: str  # 노드 이름 또는 Tool 이름
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
    seq: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: list[Subscriber] = []
        self._seq = itertools.count(1)

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        if fn in self._subs:
            self._subs.remove(fn)

    def publish(self, event: Event) -> Event:
        event.seq = next(self._seq)
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:  # noqa: BLE001 — 구독자 실패가 대화를 멈추면 안 됨 (F3013)
                pass
        return event

    def emit(self, session_id: str, type_: EventType, name: str, **payload: Any) -> Event:
        return self.publish(Event(session_id=session_id, type=type_, name=name, payload=payload))


bus = EventBus()  # 앱 전체에서 쓰는 기본 버스
