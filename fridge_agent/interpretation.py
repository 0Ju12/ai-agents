import re
from datetime import date, timedelta
from pydantic import BaseModel, Field, ValidationError
import gateway
from domain.catalog import canonical
from domain.training import GOALS, LEVELS, MOVES
from storage import today

COMMANDS = set(
    "추가 삭제 시간 부위 목표 추천 물 수면 외식 집밥 메뉴 대체 조리 섭취 요리코치 레시피 식품영양 검색 영양 도움말 입고 포장삭제 분량확인 레시피찜 찜해제 설정 운동완료 쇼핑 영상 헬스장 일정조회 일정등록 미국영양 운동자료 건강연동 시간대 주간계획 레시피저장 확인 장바구니담기 구매완료 장바구니삭제 사진식사 데모 영상링크 알림추가 알림삭제 알림토글 영양제복용 건강체크 건강반영 건강반영해제 내루틴저장 내루틴삭제 질문 섭취삭제".split()
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
    level: str | None = None
    area: str | None = Field(default=None, max_length=60)
    end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


BODY_WORDS = {
    "다리": "하체", "허벅지": "하체", "엉덩이": "하체", "하체": "하체", "스쿼트": "하체",
    "복근": "코어", "뱃살": "코어", "배": "코어", "코어": "코어", "허리": "코어",
    "팔뚝": "팔", "이두": "팔", "삼두": "팔", "팔": "팔", "어깨": "어깨", "가슴": "가슴", "등": "등",
    "상체": "상체", "전신": "전신", "유산소": "전신",
}
LEVEL_WORDS = {"초보": "초보", "입문": "초보", "처음": "초보", "중급": "중급", "고급": "숙련", "숙련": "숙련", "헬창": "숙련", "상급": "숙련"}


def body_of(text):
    text = text or ""
    return next((v for k, v in sorted(BODY_WORDS.items(), key=lambda x: -len(x[0])) if k in text), None)


def level_of(text):
    return next((v for k, v in LEVEL_WORDS.items() if k in (text or "")), None)


def workout(text):
    """'어깨 운동 30분 하고 싶어', '초보 하체 루틴' → 운동 요청. 헬스장 찾기는 제외."""
    if "헬스장" in text or not any(w in text for w in ("운동", "루틴", "트레이닝", "홈트", "스트레칭", "근력")):
        return None
    span = re.search(r"(\d{1,3})\s*분", text)
    minutes = int(span[1]) if span and 5 <= int(span[1]) <= 120 else None
    return Intent(action="운동", body=body_of(text), minutes=minutes, level=level_of(text))


QUESTION = re.compile(r"(\?|얼마|몇\s*(시간|g|그램|잔|분|번|일|kcal)|어떻게|뭐야|뭔가요|무엇|왜|괜찮|해야\s*(해|돼|하나|할까)|돼\?|되나요?|될까|좋아\?|좋을까|맞아\?|차이)")
NOT_QUESTION = re.compile(r"(먹고\s*싶|해\s*먹|만들어|하고\s*싶|알려\s*줘.*시|챙겨|사고\s*싶|추천|후보|루틴|짜\s*줘|식단|반영|기록|넣어|추가|빼\s*줘|먹을까|뭘\s*먹|뭐\s*먹|먹지|해\s*줘$|있어\.)")


def is_question(text):
    """외부 API 로는 답할 수 없는 상식 질문인지: '단백질 하루 권장량이 얼마야?'"""
    return bool(QUESTION.search(text)) and not NOT_QUESTION.search(text)


MORE = re.compile(r"(다른|딴|또 다른|더)\s*(추천|후보|메뉴|거|것|요리|레시피|선택지)")


def parse(text, emit, allow_command=True):
    command, _, arg = text.strip().partition(" ")
    arg = arg.strip()
    if MORE.search(text) and "운동" not in text:  # "다른 추천 후보 알려줘" → 되묻지 않고 다음 후보
        return Intent(action="추천", argument="더보기")
    if is_question(text) and not (allow_command and command in COMMANDS and not re.search(r"[?]|얼마|몇|어떻게|왜", arg)):
        return Intent(action="질문", argument=text[:300])  # F3022: 근거 문서 검색으로
    if allow_command and command in COMMANDS:
        return Intent(action=command, argument=arg)
    rule_workout = workout(text)
    if rule_workout and (rule_workout.body or rule_workout.minutes or rule_workout.level):
        return rule_workout  # 부위·시간·숙련도가 분명한 운동 요청은 모델 없이 바로
    if gateway.configured():
        from pydantic import ValidationError

        try:
            obj = gateway.decide(
                "Planner",
                "한국어 요청을 해석한다. action은 추천, 검색, 메뉴, 레시피, 식품영양, 쇼핑, 영상, 운동, 헬스장, 외식, 집밥, 질문, 확인 중 하나. 영양 권장량·식품 보관·운동 상식처럼 외부 API로 확인할 수 없는 질문은 질문이고 argument 는 질문 문장이다. 운동하고 싶다는 요청(부위·시간·숙련도)은 운동이고 minutes 는 운동 시간이다. 헬스장은 특정 지역의 헬스장을 찾을 때만 쓰고 argument 는 지역명이다. 재고에 있다고 명시한 재료만 add, 다 쓴 재료만 remove. 질문과 가정은 변경하지 않는다. 명시한 조건만 반환. 필드: action,argument,add,remove,minutes,goal,body,diet,day,start,end,area,budget_krw,level(초보·중급·숙련). 불명확하면 확인과 짧은 질문.",
                {"text": text, "today": today().isoformat(), "goals": list(GOALS), "body": list(MOVES)},
            )
            intent = Intent.model_validate(obj)
            if intent.action == "헬스장" and body_of(intent.argument):  # '어깨'를 지역으로 검색하지 않는다
                intent.action, intent.body, intent.argument = "운동", body_of(intent.argument), ""
            if intent.body and intent.body not in MOVES:
                intent.body = body_of(intent.body)
            if intent.level and intent.level not in LEVELS:
                intent.level = level_of(intent.level)
            if intent.action not in {
                "추천",
                "검색",
                "메뉴",
                "레시피",
                "식품영양",
                "쇼핑",
                "영상",
                "운동",
                "질문",
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
    if not intent.diet and "단백질" in text:
        intent.diet = "단백질 우선"
    if not intent.diet and any(w in text for w in ("채식", "비건")):
        intent.diet = "식물성"
    if "헬스장" in text:
        return Intent(action="헬스장", argument=text.split("헬스장")[0].strip())
    if rule_workout:
        return rule_workout
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
        or any(w in text for w in ("먹고 싶", "뭐 먹", "먹을", "먹자", "배고", "저녁", "점심", "아침", "해먹", "만들", "요리", "식사", "메뉴", "인분"))
    ):
        hello = re.search(r"(안녕|하이|hello|hi\b|반가)", text, re.I)
        return Intent(
            action="확인",
            argument=("안녕하세요! " if hello else "")
            + "무엇을 도와드릴까요? 예를 들어 ‘저녁 추천해줘’, ‘두부 사고 싶어’, ‘어깨 운동 30분 하고 싶어’, ‘물 2시간마다 알려줘’처럼 말해 주세요.",
        )
    return intent
