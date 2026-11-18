"""Tool 정의서(docs/tool-spec.md)를 등록된 Tool 목록에서 생성한다 — 코드와 문서가 어긋나지 않게.

    python scripts/gen_tool_spec.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.tools import registry  # noqa: E402
from backend.tools.base import Err, NON_RETRYABLE  # noqa: E402

lines = [
    "# Tool 정의서",
    "",
    "> `python scripts/gen_tool_spec.py` 로 생성한 문서입니다. 직접 고치지 말고 `backend/tools/__init__.py` 를 고친 뒤 다시 생성하세요.",
    "",
    "## 공통 응답 형식",
    "",
    "```json",
    '{"ok": true, "data": {...}, "meta": {"tool": "이름", "elapsed_ms": 12.3}}',
    '{"ok": false, "error": {"code": "INVALID_KEY", "message": "..."}, "meta": {...}}',
    "```",
    "",
    "Tool 은 예외를 밖으로 던지지 않습니다. 외부 API 오류 원문(키가 든 URL 포함)은 메시지에 넣지 않습니다.",
    "",
    "## 실패 코드",
    "",
    "| 코드 | 재계획 대상 |",
    "| --- | --- |",
]
for name in [v for k, v in vars(Err).items() if not k.startswith("_")]:
    lines.append(f"| {name} | {'아니오 (다시 해도 같음)' if name in NON_RETRYABLE else '예'} |")
lines += ["", "## Tool 목록", ""]
for t in registry._tools.values():  # noqa: SLF001 — 문서 생성 전용
    req = t.parameters.get("required", [])
    lines += [f"### {t.name}", "", f"- 언제 쓰나: {t.description}", f"- 종류: {'외부 API 툴' if t.kind == 'external' else '로컬 서버 툴'}",
              f"- 요구사항: {', '.join(t.tags)}", f"- 필수 인자: {', '.join(req) or '없음'}", "", "```json",
              json.dumps(t.parameters, ensure_ascii=False, indent=2), "```", ""]
(ROOT / "docs" / "tool-spec.md").write_text("\n".join(lines), encoding="utf-8")
print(f"docs/tool-spec.md — Tool {len(registry.names())}개")
