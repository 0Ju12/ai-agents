"""Access contracts for all agent tools. This metadata is also served at /api/tools."""

from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal


class ToolReply(BaseModel):
    ok: bool
    data: Any = None
    source: str | None = None
    error: str | None = None


class Task(BaseModel):
    tool: str
    argument: str = Field(max_length=500)
    fixed: bool = True
    purpose: str

    @field_validator("tool")
    @classmethod
    def registered(cls, value):
        if value not in META:
            raise ValueError("등록되지 않은 도구입니다.")
        return value


class WorkerResult(BaseModel):
    task: Task
    result: dict
    decision: Literal["complete", "skip", "escalate"] = "complete"
    attempts: int = 1


META = {
    "search": ("외부", "TheMealDB 재료별 후보", "재료명", "[{id,title}]"),
    "detail": ("외부", "TheMealDB 후보 상세", "후보 id", "{title,ingredients,instructions}"),
    "nutrition": (
        "외부",
        "Open Food Facts 제품 표시 영양",
        "제품 바코드 8~14자리",
        "{product,basis,kcal,protein_g}",
    ),
    "kr_recipe": ("외부", "식품안전나라 국내 레시피", "메뉴명", "[{id,메뉴,재료·분량,조리 순서}]"),
    "kr_nutrition": ("외부", "식약처 식품영양성분", "식품명", "[{식품,기준량,열량(kcal),단백질(g)}]"),
    "usda": ("외부", "USDA 100g 영양 참조", "영어 식품명", "[{id,title,url,nutrients_per_100g}]"),
    "naver": ("외부", "네이버 장보기", "제품 검색어", "[{id,title,price_krw,merchant,url}]"),
    "coupang": ("외부", "쿠팡 파트너스 상품 검색", "제품 검색어", "[{id,title,price_krw,merchant,url}]"),
    "youtube": (
        "외부",
        "YouTube 최근 30일 요리 영상",
        "메뉴명",
        "[{title,url,published,views,views_per_day}]",
    ),
    "instagram": ("외부", "Instagram 최근 해시태그", "메뉴명", "[{title,url,published,likes,comments}]"),
    "gyms": ("외부", "Kakao 지역 헬스장", "지역·역명", "[{id,title,url,address}]"),
    "wger": ("외부", "wger 운동 참고자료", "운동 id", "{id,title,equipment,url,license}"),
    "knowledge": (
        "로컬 벡터 DB + 외부 임베딩",
        "2회차 색인 근거 검색",
        "질문",
        "[{id,title,excerpt,url,distance}]",
    ),
    "calendar_list": ("로컬 / 외부", "지정일 등록 일정 조회", "YYYY-MM-DD", "[{id,title,start,end}]"),
    "calendar_register": (
        "로컬 / 외부",
        "저장 계획 일정 등록",
        "저장한 계획 id",
        "{id,title,start,end,day}",
    ),
    "local": ("로컬", "재료·식사·운동 계산", "현재 조건", "{메뉴?,안내?,근거?,루틴?}"),
    "vision": ("외부 모델", "사진 속 음식·재료 후보 (사용자 확인 후 기록)", "meal 또는 fridge 사진", "[{name,grams?,count?,confidence}]"),
    "cook_guide": ("로컬 + 모델", "레시피를 단계 카드(동작·재료·g·타이머·사진)로 구조화", "메뉴 또는 국내 레시피 id", "{단계:[{설명,동작,재료,타이머(초),사진}]}"),
}
ERRORS = [
    "INVALID_INPUT",
    "MISSING_KEY",
    "NO_RESULT",
    "SOURCE_UNAVAILABLE",
    "AUTH_FAILED",
    "RATE_LIMIT",
    "PROVIDER_ERROR",
    "NO_INDEX",
    "CALENDAR_NOT_CONNECTED",
    "RAG_DEPENDENCY_MISSING",
    "TIME_BUDGET",
]


def definitions():
    return {
        k: {
            "name": k,
            "kind": a,
            "description": b,
            "input": {"type": "string", "description": c},
            "output": d,
            "envelope_schema": ToolReply.model_json_schema(),
            "errors": ERRORS,
        }
        for k, (a, b, c, d) in META.items()
    }
