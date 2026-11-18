"""앱 전역 객체: 저장소와 로깅 Agent 를 한 번만 만들어 이벤트 버스에 붙인다."""

from __future__ import annotations

from functools import lru_cache

from backend.config import DB_PATH
from backend.events.bus import bus
from backend.logging_agent.agent import LoggingAgent
from backend.store.db import Store


@lru_cache
def get_store() -> Store:
    store = Store(DB_PATH)
    LoggingAgent(store).attach(bus)
    return store
