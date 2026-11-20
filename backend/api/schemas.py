"""요청·응답 형식 (F3017)."""

from __future__ import annotations

from datetime import date,time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatOut(BaseModel):
    session_id: str
    answer: str
    intent: str | None
    replans: int
    steps: list[dict[str, Any]]  # 실행 단계·Tool 호출 이력 (F3019)


class PlanFields(BaseModel):
    @field_validator("trip_date",check_fields=False)
    @classmethod
    def valid_day(cls,value):
        if value is not None:date.fromisoformat(value)
        return value
    @field_validator("start_time","end_time",check_fields=False)
    @classmethod
    def valid_clock(cls,value):
        if value is not None:time.fromisoformat(value)
        return value
    @model_validator(mode="after")
    def ordered(self):
        if self.start_time and self.end_time and self.start_time>=self.end_time:
            raise ValueError("종료 시각은 시작 시각 이후로 입력하세요.")
        return self

class PlanIn(PlanFields):
    title: str = Field(min_length=1, max_length=100)
    trip_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    items: list[dict[str, Any]] = []


class PlanPatch(PlanFields):
    title: str | None = Field(default=None,min_length=1,max_length=100)
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



class LogSession(BaseModel):
    session_id: str
    events: int
    started_at: str
    ended_at: str
    replans: int
    tool_calls: int


class LogEvent(BaseModel):
    id: int
    session_id: str
    seq: int
    type: str
    name: str
    payload: dict[str, Any]
    ts: str
