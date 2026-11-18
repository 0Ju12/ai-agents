"""Agent 상태 — 단계 사이에 넘기는 값 (명세서 2.4절)."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Intent = Literal["plan_trip", "route_only", "ask_heritage", "chitchat"]


class Conditions(TypedDict, total=False):
    date: str  # YYYY-MM-DD — 기준 조건
    origin: str  # 출발지
    region: str  # 목적 지역 (시도)
    mode: str  # train / express / intercity / car / transit
    return_by: str  # HH:MM — 제약 조건
    mix: dict[str, int]  # {"heritage": 2, "attraction": 1, "lunch": 1, "cafe": 1} — 선호 조건
    food: str  # 음식 취향
    stay_min: int | None  # 사용자가 정한 체류시간 (없으면 역산)


class Step(TypedDict):
    tool: str
    args: dict[str, Any]


class TripState(TypedDict, total=False):
    session_id: str
    message: str
    intent: Intent
    conditions: Conditions
    missing: list[str]  # 판단에 필요한데 빠진 조건 → 되묻기
    plan: list[Step]
    results: dict[str, dict]  # Tool 이름(+인덱스)별 결과 — 재계획 때 재사용
    verdict: dict[str, Any]  # {"ok": bool, "reasons": [...], "excluded": [...]}
    replan_count: int
    answer: str
