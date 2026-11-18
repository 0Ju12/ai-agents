"""요청·응답 형식 (F3017)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatOut(BaseModel):
    session_id: str
    answer: str
    intent: str | None
    replans: int
    steps: list[dict[str, Any]]  # 실행 단계·Tool 호출 이력 (F3019)


class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    trip_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    items: list[dict[str, Any]] = []


class PlanPatch(BaseModel):
    title: str | None = None
    trip_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    items: list[dict[str, Any]] | None = None


class PlanOut(BaseModel):
    id: int
    title: str
    trip_date: str
    start_time: str
    end_time: str
    items: list[dict[str, Any]]
    created_at: str


class PlanSaved(BaseModel):
    plan: PlanOut
    overlaps: list[PlanOut]  # 같은 날 시간이 겹치는 기존 계획 (저장은 막지 않음, F3015)
