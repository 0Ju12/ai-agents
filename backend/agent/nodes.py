"""메인 Agent 노드 — 의도 분석 → 조건 추출 → 계획 → 실행 → 판정 → (재계획) → 응답.

각 노드는 진입·종료 이벤트를, Tool 은 요청·응답·소요시간 이벤트를, LLM 판단은 판단과 이유를
이벤트로 발행한다 (F3012). 발행은 로깅 Agent 구현에 의존하지 않는다.

뼈대 단계: 의도 분석·조건 추출은 임시 규칙으로 동작한다.
TODO(2일차): OpenAI 모델 호출로 바꾸고, 규칙은 키가 없을 때의 대체 경로로만 남긴다.
"""

from __future__ import annotations

import re
from functools import wraps
from typing import Callable

from backend.config import MAX_REPLAN
from backend.events.bus import EventBus, bus as default_bus
from backend.tools import registry
from backend.tools.base import NON_RETRYABLE

from .state import TripState

_bus: EventBus = default_bus


def use_bus(b: EventBus) -> None:
    global _bus
    _bus = b


def node(name: str) -> Callable:
    """노드 진입·종료 이벤트를 자동으로 발행하는 장식자."""

    def deco(fn: Callable[[TripState], dict]) -> Callable[[TripState], dict]:
        @wraps(fn)
        def wrapper(state: TripState) -> dict:
            sid = state.get("session_id", "-")
            _bus.emit(sid, "node_start", name)
            out = fn(state) or {}
            _bus.emit(sid, "node_end", name, keys=sorted(out))
            return out

        return wrapper

    return deco


# ── 1. 의도 분석 ───────────────────────────────────────
_MODE_WORDS = {"ktx": "train", "기차": "train", "열차": "train", "고속버스": "express", "시외버스": "intercity",
               "자가용": "car", "차로": "car", "운전": "car", "대중교통": "transit"}


@node("analyze_intent")
def analyze_intent(state: TripState) -> dict:
    msg = state["message"]
    if re.search(r"(국보|보물|유산).*(왜|무엇|뭐야|역사|근거)", msg):
        intent, reason = "ask_heritage", "국가유산 설명·근거를 묻는 표현"
    elif re.search(r"(당일|일정|여행|가서|가고|1박|코스|짜\s*줘)", msg):
        intent, reason = "plan_trip", "날짜·지역·장소 구성 등 여행 계획 표현"
    elif re.search(r"(어떻게 가|가는 법|교통|몇 시 차)", msg):
        intent, reason = "route_only", "이동 방법만 묻는 표현"
    else:
        intent, reason = "chitchat", "Tool 이 필요 없는 일반 질문"
    _bus.emit(state["session_id"], "llm_decision", "analyze_intent", decision=intent, reason=reason, method="rule")
    return {"intent": intent}


# ── 2. 조건 추출 ───────────────────────────────────────
@node("extract_conditions")
def extract_conditions(state: TripState) -> dict:
    msg = state["message"].lower()
    cond = dict(state.get("conditions") or {})  # 대화 맥락: 이전 조건을 유지하고 바뀐 것만 갱신 (F3010)
    for word, mode in _MODE_WORDS.items():
        if word in msg:
            cond["mode"] = mode
    m = re.search(r"(\d{1,2})시\s*(?:전|까지)", msg)
    if m:
        hour = int(m.group(1))
        if hour < 12 and ("밤" in msg or "저녁" in msg or "오후" in msg):
            hour += 12
        cond["return_by"] = f"{hour:02d}:00"
    m = re.search(r"([가-힣]{2,4})에서\s", state["message"])
    if m:
        cond["origin"] = m.group(1)
    # 추출하지 못한 조건은 임의로 채우지 않고 비워 둔다
    missing = [k for k in ("origin", "mode") if not cond.get(k)] if state.get("intent") == "plan_trip" else []
    _bus.emit(state["session_id"], "llm_decision", "extract_conditions", conditions=cond, missing=missing, method="rule")
    return {"conditions": cond, "missing": missing}


# ── 3. 계획 ────────────────────────────────────────────
@node("plan")
def plan(state: TripState) -> dict:
    """필요한 Tool 만 계획에 넣는다. 인자는 조건과 앞선 결과로 채운다 (F3006, F3007).
    TODO(2일차): 장소 구성(mix)에 따라 search_tour/search_place 단계와 구간별 plan_leg 를 동적으로 생성.
    """
    cond = state.get("conditions") or {}
    intent = state["intent"]
    steps = []
    if intent == "ask_heritage":
        steps = [{"tool": "ask_heritage", "args": {"question": state["message"]}}]
    elif intent in ("plan_trip", "route_only"):
        if intent == "plan_trip" and cond.get("region"):
            steps.append({"tool": "search_heritage", "args": {"region": cond["region"], "kind": "국보"}})
        steps.append({"tool": "plan_leg", "args": {"mode": cond.get("mode", ""), "origin": {"name": cond.get("origin", "")},
                                                    "destination": {"name": cond.get("region", "")}, "date": cond.get("date", "")}})
    _bus.emit(state["session_id"], "llm_decision", "plan", steps=[s["tool"] for s in steps], method="rule")
    return {"plan": steps}


# ── 4. 실행 ────────────────────────────────────────────
@node("execute")
def execute(state: TripState) -> dict:
    """계획대로 Tool 을 부르고 결과를 보관한다. 실패해도 사유를 남기고 다음 단계로 간다 (F3007).
    이미 성공한 결과는 재계획 때 다시 부르지 않는다 (F3009)."""
    results = dict(state.get("results") or {})
    sid = state["session_id"]
    for i, step in enumerate(state.get("plan") or []):
        key = f"{i}:{step['tool']}"
        if results.get(key, {}).get("ok"):
            continue
        _bus.emit(sid, "tool_call", step["tool"], args=step["args"])
        res = registry.run(step["tool"], **step["args"])
        _bus.emit(sid, "tool_result", step["tool"], ok=res["ok"], error=res.get("error"), elapsed_ms=res["meta"]["elapsed_ms"])
        results[key] = res
    return {"results": results}


# ── 5. 판정 ────────────────────────────────────────────
@node("judge")
def judge(state: TripState) -> dict:
    """제약 판정은 코드로 한다 (F3008).
    TODO(2일차): domain.constraints.check_time_budget · check_open 으로 시간 예산·운영시간·식사 슬롯 판정.
    지금은 '재시도로 결과가 달라질 수 있는 실패'가 남았는지만 본다.
    """
    retryable, fatal = [], []
    for key, res in (state.get("results") or {}).items():
        if res["ok"]:
            continue
        (fatal if res["error"]["code"] in NON_RETRYABLE else retryable).append({"step": key, **res["error"]})
    verdict = {"ok": not retryable, "retryable": retryable, "fatal": fatal}
    return {"verdict": verdict}


@node("replan")
def replan(state: TripState) -> dict:
    """대안을 찾도록 계획을 다시 구성한다. TODO(2일차): 실패 유형별 완화 순서 적용."""
    count = state.get("replan_count", 0) + 1
    _bus.emit(state["session_id"], "replan", "replan", count=count, reasons=state["verdict"]["retryable"])
    return {"replan_count": count}


# ── 6. 응답 ────────────────────────────────────────────
@node("ask_back")
def ask_back(state: TripState) -> dict:
    labels = {"origin": "출발지", "mode": "이동 수단(KTX·고속버스·자가용 등)"}
    need = ", ".join(labels[m] for m in state["missing"])
    return {"answer": f"일정을 계산하려면 {need}이(가) 필요합니다. 알려 주시겠어요?"}


@node("respond")
def respond(state: TripState) -> dict:
    """TODO(2일차): 시간표형 일정, 구간별 교통, 제외 사유, 판단 근거, 콘텐츠를 담은 최종 응답 (F3011)."""
    if state["intent"] == "chitchat":
        return {"answer": "일반 질문으로 판단해 도구 없이 답합니다. (LLM 연결 후 실제 답변으로 바뀝니다.)"}
    verdict = state.get("verdict") or {}
    lines = []
    if state.get("replan_count", 0) >= MAX_REPLAN and not verdict.get("ok"):
        lines.append(f"재계획 {MAX_REPLAN}회 안에 조건을 만족하는 일정을 찾지 못했습니다. 조건을 조정할까요?")
    for f in verdict.get("fatal", []):
        lines.append(f"- {f['step'].split(':', 1)[1]}: {f['message']}")
    ok_steps = [k.split(":", 1)[1] for k, r in (state.get("results") or {}).items() if r["ok"]]
    if ok_steps:
        lines.append("확인한 정보: " + ", ".join(ok_steps))
    return {"answer": "\n".join(lines) or "일정 응답 생성은 2일차에 구현합니다."}


# ── 라우팅 ─────────────────────────────────────────────
def route_after_extract(state: TripState) -> str:
    if state["intent"] == "chitchat":
        return "respond"
    if state.get("missing"):
        return "ask_back"
    return "plan"


def route_after_judge(state: TripState) -> str:
    if state["verdict"]["ok"]:
        return "respond"
    if state.get("replan_count", 0) >= MAX_REPLAN:
        return "respond"  # 상한 도달 → 멈추고 사유와 함께 응답 (F3009, NF3004)
    return "replan"
