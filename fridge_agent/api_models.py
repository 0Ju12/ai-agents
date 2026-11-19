from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ScreenState(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    day: str = Field(alias="날짜")
    stock: list[str] = Field(alias="냉장고")
    lots: list[dict] = Field(alias="포장")
    plan: dict = Field(alias="계획")
    journal: dict = Field(alias="오늘 기록")
    health: dict = Field(alias="건강")
    settings: dict = Field(alias="설정")


class ChatReply(ScreenState):
    steps: list[list[str]] = Field(alias="실행 단계")
    events: list[dict] = Field(alias="추적")
    run_id: str = Field(alias="실행 ID")
    current: dict = Field(alias="현재 추천")
