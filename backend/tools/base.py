"""Tool 계약 (F3001).

- 성공도 실패도 같은 모양: {"ok": True, "data": ...} / {"ok": False, "error": {"code", "message"}}
- Tool 은 예외를 밖으로 던지지 않는다. 어떤 예외든 실패 응답으로 바꾼다 (NF3003).
- Agent 에게는 이름 · 설명(언제 쓰는지) · 입력 스키마만 넘긴다.
- 외부 API 오류 원문에는 키가 든 URL 이 섞일 수 있으므로 메시지에 넣지 않는다 (NF3002).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


class Err:
    """실패 코드. 도메인 코드는 Tool 정의서와 같은 이름을 쓴다."""

    BAD_ARGUMENT = "BAD_ARGUMENT"  # 입력이 규격과 다름
    INVALID_KEY = "INVALID_KEY"  # 키가 없거나 틀림 — 다시 해도 같으므로 재계획하지 않음
    NOT_FOUND = "NOT_FOUND"  # 없는 식별자
    NO_DATA = "NO_DATA"  # 조회는 됐지만 결과가 비었음
    UPSTREAM_ERROR = "UPSTREAM_ERROR"  # 외부 API 시간 초과 · 서버 오류
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"  # 뼈대 단계에서 아직 구현하지 않음
    # 도메인 코드
    NO_PLACE = "NO_PLACE"
    NO_COORD = "NO_COORD"
    CLOSED = "CLOSED"
    NO_HOURS = "NO_HOURS"
    NO_SERVICE = "NO_SERVICE"
    AMBIGUOUS_STATION = "AMBIGUOUS_STATION"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    NO_INDEX = "NO_INDEX"


# 다시 시도해도 결과가 같은 실패 — 재계획 대상에서 뺀다 (명세서 2.4절)
NON_RETRYABLE = {Err.INVALID_KEY, Err.BAD_ARGUMENT, Err.NOT_IMPLEMENTED, Err.QUOTA_EXCEEDED}


def ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


@dataclass
class Tool:
    name: str
    description: str  # 기능이 아니라 '언제 쓰는지'를 적는다 (명세서 2.3절)
    parameters: dict  # JSON Schema
    func: Callable[..., dict]
    kind: Literal["external", "local"] = "external"
    tags: list[str] = field(default_factory=list)

    def run(self, **kwargs) -> dict:
        """계약을 강제하는 실행기. 소요 시간을 meta 로 붙인다 (F3012 이벤트용)."""
        started = time.perf_counter()
        try:
            result = self.func(**kwargs)
            if not isinstance(result, dict) or "ok" not in result:
                result = fail(Err.UPSTREAM_ERROR, f"{self.name} 가 계약에 맞지 않는 값을 돌려줬습니다.")
        except TypeError:
            result = fail(Err.BAD_ARGUMENT, "입력값이 규약과 다릅니다.")
        except Exception:  # noqa: BLE001 — 어떤 예외도 밖으로 내보내지 않는다
            result = fail(Err.UPSTREAM_ERROR, f"{self.name} 실행 중 오류가 났습니다.")
        result["meta"] = {"tool": self.name, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
        return result

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"이미 등록된 Tool 이름입니다: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def run(self, name: str, **kwargs) -> dict:
        tool = self.get(name)
        if tool is None:
            return fail(Err.NOT_FOUND, f"등록되지 않은 Tool 입니다: {name}")
        return tool.run(**kwargs)

    def catalog(self, names: list[str] | None = None) -> list[dict]:
        """Agent 에게 넘기는 목록 — 이름 · 설명 · 입력 스키마만."""
        tools = self._tools.values() if names is None else [self._tools[n] for n in names if n in self._tools]
        return [t.spec() for t in tools]

    def names(self) -> list[str]:
        return list(self._tools)
