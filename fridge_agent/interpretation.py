import re
from datetime import date, timedelta
from pydantic import BaseModel, Field, ValidationError
import gateway
from domain.catalog import canonical
from domain.training import GOALS, MOVES
from storage import today

COMMANDS = set(
    "추가 삭제 시간 부위 목표 추천 물 수면 외식 집밥 메뉴 대체 조리 섭취 요리코치 레시피 식품영양 검색 영양 도움말 입고 포장삭제 설정 운동완료 쇼핑 영상 헬스장 해설 일정조회 일정등록 미국영양 운동자료 건강연동 시간대 주간계획 레시피저장 확인 장바구니담기 구매완료 장바구니삭제 사진식사".split()
)


class Intent(BaseModel):
    action: str = "추천"
    argument: str = Field(default="", max_length=500)
    add: list[str] = Field(default_factory=list, max_length=40)
    remove: list[str] = Field(default_factory=list, max_length=40)
    minutes: int | None = Field(default=None, ge=1, le=240)
    goal: str | None = None
    body: str | None = None
    diet: str | None = None
    day: date | None = None
    budget_krw: int | None = Field(default=None, ge=0, le=10000000)
    area: str | None = Field(default=None, max_length=60)
    end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def parse(text, emit):
    command, _, arg = text.strip().partition(" ")
    arg = arg.strip()
    if command in COMMANDS:
        return Intent(action=command, argument=arg)
    if gateway.configured():
        from pydantic import ValidationError

        try:
            obj = gateway.decide(
                "Planner",
                "한국어 요청을 해석한다. action은 추천, 검색, 메뉴, 레시피, 식품영양, 해설, 쇼핑, 영상, 헬스장, 외식, 집밥, 확인 중 하나. 재고에 있다고 명시한 재료만 add, 다 쓴 재료만 remove. 질문과 가정은 변경하지 않는다. 명시한 조건만 반환. 필드: action,argument,add,remove,minutes,goal,body,diet,day,start,end,area,budget_krw. 불명확하면 확인과 짧은 질문.",
                {"text": text, "today": today().isoformat(), "goals": list(GOALS), "body": list(MOVES)},
            )
            intent = Intent.model_validate(obj)
            if intent.action not in {
                "추천",
                "검색",
                "메뉴",
                "레시피",
                "식품영양",
                "해설",
                "쇼핑",
                "영상",
                "헬스장",
                "외식",
                "집밥",
                "확인",
            }:
                raise ValueError("action")
            emit(
                "llm_decision",
                "Planner",
                method="model",
                decision=intent.action,
                reason="자연어의 명시적 조건 추출",
            )
            return intent
        except (ValueError, OSError, KeyError, IndexError):
            emit("error", "모델 연결", reason="명령·로컬 해석 사용")
    intent = Intent()
    times = re.findall(r"(?:[01]\d|2[0-3]):[0-5]\d", text)
    if times:
        intent.start = times[0]
    if len(times) > 1:
        intent.end = times[1]
    money = re.search(r"([0-9,]+)\s*(만)?원", text)
    if money:
        intent.budget_krw = min(10000000, int(money[1].replace(",", "")) * (10000 if money[2] else 1))
    if "내일" in text:
        intent.day = today() + timedelta(days=1)
    elif "오늘" in text:
        intent.day = today()
    span = re.search(r"(\d{1,3})\s*분", text)
    if span and 1 <= int(span[1]) <= 240:
        intent.minutes = int(span[1])
    intent.goal = next((v for v in GOALS if v in text), None)
    intent.body = next((v for v in MOVES if v in text), None)
    intent.diet = next((v for v in ("식물성", "단백질 우선", "균형") if v in text), None)
    if any(x in text for x in ("유산", "유적", "국보", "석굴암", "불국사")):
        return Intent(action="해설", argument=text)
    if "헬스장" in text:
        return Intent(action="헬스장", argument=text.split("헬스장")[0].strip())
    if "외식" in text and "?" not in text:
        intent.action = "외식"
    if "집밥" in text:
        intent.action = "집밥"
    request = re.search(
        r"(.+?)(?:이|가|은|는|을|를)?\s*(?:다 떨어졌|다 먹었|다 썼|있어|있다|넣었|샀어)", text
    )
    declarative = request and (
        "?" not in text or text[request.end() :].lstrip().startswith((".", "!", ","))
    )
    if declarative and not any(x in text for x in ("있으면", "있어야", "있어도", "있다고 가정")):
        segment = re.sub(r"^.*?(?:냉장고에|오늘은 |지금 )", "", request[1]).strip()
        entries = [
            canonical(re.sub(r"(?:이|가|은|는|을|를)$", "", x.strip()))
            for x in re.split(r"\s*(?:,|하고|와 |과 |랑 |이랑 )\s*", segment)
            if x.strip()
        ]
        if any(x in request[0] for x in ("다 먹", "다 썼", "떨어")):
            intent.remove = entries
        else:
            intent.add = entries
    if not (
        any(
            [
                intent.minutes,
                intent.start,
                intent.budget_krw,
                intent.goal,
                intent.body,
                intent.day,
                intent.diet,
                intent.add,
                intent.remove,
            ]
        )
        or intent.action != "추천"
        or "추천" in text
    ):
        return Intent(
            action="확인",
            argument="재료 등록, 식단, 운동 중 어떤 도움이 필요한가요? 예를 들어 ‘추가 두부, 달걀’이라고 입력해 주세요.",
        )
    return intent
