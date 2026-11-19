"""조리 모드: 레시피 문장을 단계 카드(동작·재료·분량·시간·불 세기·사진)로 구조화한다.

판단 순서
    1. 규칙: 동작 단어, 'N분', 불 세기, 레시피 재료 이름을 문장에서 찾는다.
    2. 모델(선택): 규칙이 못 찾은 동작·재료를 보충한다.
    3. 코드 검증: 모델이 낸 재료는 레시피 재료 목록에 있는 것만, 시간은 원문에 적힌 숫자만 받는다.
       분량은 레시피의 1인분 g 에 인분 수를 곱한 값만 쓴다 (모델이 숫자를 만들지 않는다).
"""

import os
import re
from typing import Literal

from pydantic import BaseModel, Field

import gateway
from agent_roles import recipe_ingredients
from domain.catalog import canonical

# 동작 → (화면 애니메이션 이름, 문장에서 찾는 단어). 앞에 있을수록 우선한다.
ACTIONS = {
    "썰기": ("chop", ("썰", "다지", "채 ", "채를", "깍둑", "자르", "손질")),
    "데치기": ("blanch", ("데치", "데쳐")),
    "볶기": ("stir", ("볶",)),
    "끓이기": ("boil", ("끓", "삶")),
    "찌기": ("steam", ("찌", "찜기", "쪄")),
    "굽기": ("grill", ("굽", "구워", "부치", "부쳐", "지지")),
    "섞기": ("mix", ("섞", "버무", "풀어", "젓", "저어", "개어")),
    "넣기": ("drop", ("넣", "붓", "부어", "담", "올리", "곁들")),
    "준비": ("ready", ()),
}
HEAT = ("센불", "강불", "중강불", "중불", "중약불", "약불")
ICONS = {
    "달걀": "🥚", "두부": "🧈", "양파": "🧅", "대파": "🌿", "마늘": "🧄", "감자": "🥔", "당근": "🥕",
    "버섯": "🍄", "양송이버섯": "🍄", "토마토": "🍅", "브로콜리": "🥦", "시금치": "🥬", "배추": "🥬",
    "김치": "🥬", "고추": "🌶️", "고춧가루": "🌶️", "닭가슴살": "🍗", "닭고기": "🍗", "돼지고기": "🥩",
    "소고기": "🥩", "참치": "🐟", "새우": "🦐", "생선": "🐟", "밥": "🍚", "쌀": "🍚", "면": "🍜", "국수": "🍜",
    "우유": "🥛", "플레인요거트": "🥛", "치즈": "🧀", "버터": "🧈", "바나나": "🍌", "딸기": "🍓", "사과": "🍎",
    "오이": "🥒", "옥수수": "🌽", "빵": "🍞", "오트밀": "🥣", "간장": "🫙", "식용유": "🫗", "참기름": "🫗",
    "올리브유": "🫒", "소금": "🧂", "설탕": "🧂", "물": "💧", "레몬": "🍋", "깨": "🌰", "콩": "🫘",
    "닭다리살": "🍗", "고등어": "🐟", "연어": "🍣", "애호박": "🥒", "가지": "🍆", "양배추": "🥬", "무": "🥢",
    "콩나물": "🌱", "파프리카": "🫑", "파스타": "🍝", "소면": "🍜", "식빵": "🍞", "김": "🍙", "미역": "🌿",
    "밀가루": "🌾", "된장": "🥣", "아보카도": "🥑", "아몬드": "🥜", "블루베리": "🫐", "렌틸콩": "🫘",
}


def icon(name):
    name = canonical(name)
    return ICONS.get(name) or next((v for k, v in ICONS.items() if k in name), "🥣")


class StepDraft(BaseModel):
    """모델이 단계마다 채울 양식."""

    index: int = Field(ge=0, le=40)
    action: Literal["썰기", "데치기", "볶기", "끓이기", "찌기", "굽기", "섞기", "넣기", "준비"]
    ingredients: list[str] = Field(default_factory=list, max_length=12)
    tip: str = Field(default="", max_length=80, description="원문에 있는 주의점만 짧게. 없으면 빈 문자열")


class GuideDraft(BaseModel):
    steps: list[StepDraft] = Field(default_factory=list, max_length=40)


GUIDE_PROMPT = (
    "레시피의 각 단계 문장에서 대표 동작 하나와 그 단계에 쓰는 재료를 고른다. 재료는 주어진 재료 목록의 이름만 쓴다. "
    "분량·시간·온도 숫자는 쓰지 않는다. 원문에 없는 내용을 더하지 않는다."
)


def clean(text):
    """식약처 원문의 '1. ' 번호와 끝에 붙은 단계 기호(a, b)를 지운다."""
    text = re.sub(r"^\s*\d+\s*[.)]\s*", "", str(text or "")).strip()
    return re.sub(r"[a-z]$", "", text).strip()


def detect_action(text):
    for name, (_, words) in ACTIONS.items():
        if any(w in text for w in words):
            return name
    return "준비"


def timer_seconds(text):
    m = re.search(r"(\d{1,3})\s*분", text)
    s = re.search(r"(\d{1,3})\s*초", text)
    total = (int(m[1]) * 60 if m else 0) + (int(s[1]) if s else 0)
    return total if 0 < total <= 3 * 3600 else None


def mentioned(text, names):
    return [n for n in names if n and (n in text or canonical(n) in text)]


def build(title, steps, grams=None, raw_ingredients=None, photos=None, servings=1, stock=(), source="", emit=None):
    """단계 카드 목록을 만든다. grams 는 1인분 재료 g, raw_ingredients 는 식약처 재료 원문."""
    emit = emit or (lambda *a, **k: None)
    if not 1 <= servings <= 20:
        raise ValueError("1~20인분으로 입력하세요.")
    texts = [clean(t) for t in steps if clean(t)][:40]
    if not texts:
        raise ValueError("조리 단계가 있는 레시피를 선택하세요.")
    grams = {canonical(k): float(v) for k, v in (grams or {}).items()}
    names = list(grams) or [canonical(n) for n in recipe_ingredients(raw_ingredients)]
    have = {canonical(x) for x in stock}
    photos = list(photos or [])
    cards = []
    for i, text in enumerate(texts):
        action = detect_action(text)
        cards.append(
            {
                "순서": i + 1,
                "설명": text,
                "동작": action,
                "애니메이션": ACTIONS[action][0],
                "재료": mentioned(text, names),
                "타이머(초)": timer_seconds(text),
                "불 세기": next((h for h in HEAT if h in text), None),
                "사진": photos[i] if i < len(photos) else None,
                "팁": "",
            }
        )
    method = "규칙"
    if os.getenv("GUIDE_LLM", "1") == "1" and gateway.configured():
        try:
            draft = gateway.structured(
                "조리 가이드",
                GUIDE_PROMPT,
                {"menu": title, "ingredients": names, "steps": texts},
                GuideDraft,
            )
            allowed = set(names)
            for d in draft.steps:
                if not 0 <= d.index < len(cards):
                    continue
                card = cards[d.index]
                if card["동작"] == "준비" and d.action != "준비":  # 규칙이 못 찾은 동작만 보충
                    card["동작"], card["애니메이션"] = d.action, ACTIONS[d.action][0]
                extra = [canonical(x) for x in d.ingredients if canonical(x) in allowed and canonical(x) not in card["재료"]]
                card["재료"] += extra
                if d.tip and any(w in card["설명"] for w in re.findall(r"[가-힣]{2,}", d.tip)[:3]):
                    card["팁"] = d.tip  # 원문 단어와 겹치는 팁만
            method = "규칙 + 모델 보충(코드 검증)"
            emit("llm_decision", "조리 가이드", method="model", decision=len(draft.steps), reason="단계별 동작·재료 구조화")
        except (ValueError, OSError):
            emit("error", "조리 가이드", reason="규칙 구조화만 사용")
    for card in cards:
        card["재료"] = [
            {
                "이름": n,
                "아이콘": icon(n),
                "분량(g)": round(grams[n] * servings, 1) if n in grams else None,
                "보유": n in have,
            }
            for n in card["재료"]
        ]
    return {
        "메뉴": title,
        "인분": servings,
        "출처": source,
        "판단 방법": method,
        "대표 아이콘": icon(names[0]) if names else "🍽️",
        "재료 합계": [
            {"이름": n, "아이콘": icon(n), "분량(g)": round(grams[n] * servings, 1) if n in grams else None, "보유": n in have}
            for n in names
        ],
        "단계": cards,
        "안내": "분량은 1인분 레시피 g 에 인분 수를 곱한 값입니다. 원문에 g 이 없으면 비워 둡니다.",
    }
