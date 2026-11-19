"""상황 문장에서 원하는 메뉴·종류를 읽어 레시피를 고른다 (규칙, 모델 없이).

    "김치찌개 먹고 싶어"   → 제목에 '김치찌개'가 든 레시피
    "파스타 해먹고 싶어"   → 파스타 레시피
    "고기 먹고 싶어"       → 소고기·돼지고기·닭 레시피
    "다이어트 중인데 저녁" → 열량이 낮은 순
"""

import json
import re
from functools import lru_cache
from pathlib import Path

CATEGORIES = {
    "고기": {"ing": {"소고기", "돼지고기", "닭가슴살", "닭다리살"}},
    "육류": {"ing": {"소고기", "돼지고기", "닭가슴살", "닭다리살"}},
    "소고기": {"ing": {"소고기"}}, "돼지고기": {"ing": {"돼지고기"}}, "닭": {"ing": {"닭가슴살", "닭다리살"}}, "치킨": {"ing": {"닭가슴살", "닭다리살"}},
    "생선": {"ing": {"고등어", "연어", "참치"}}, "해산물": {"ing": {"새우"}}, "새우": {"ing": {"새우"}},
    "면": {"ing": {"소면", "파스타"}}, "국수": {"ing": {"소면"}}, "파스타": {"ing": {"파스타"}},
    "밥": {"title": ("밥",)}, "덮밥": {"title": ("덮밥",)}, "볶음밥": {"title": ("볶음밥",)}, "김밥": {"title": ("김밥",)},
    "국": {"title": ("국", "찌개", "수프")}, "국물": {"title": ("국", "찌개", "수프")}, "찌개": {"title": ("찌개",)}, "수프": {"title": ("수프",)}, "따뜻한": {"title": ("국", "찌개", "수프", "죽")},
    "샐러드": {"title": ("샐러드",)}, "토스트": {"ing": {"식빵"}}, "빵": {"ing": {"식빵"}}, "샌드위치": {"ing": {"식빵"}},
    "전": {"title_end": ("전",)}, "부침개": {"title_end": ("전",)}, "반찬": {"title": ("무침", "볶음", "조림", "나물")},
    "간식": {"title": ("요거트", "스무디", "맛탕", "오트밀", "구이")}, "아침": {"title": ("오트밀", "토스트", "스무디", "요거트", "죽", "달걀")},
}
LIGHT = ("다이어트", "가볍게", "가벼운", "저칼로리", "살 빼", "체중")
STOP = {"오늘", "저녁", "점심", "아침", "나", "좀", "뭔가", "그냥", "지금", "우리", "같이", "둘이", "둘이서", "혼자", "간단히", "간단한"}


@lru_cache(maxsize=1)
def ingredient_names():
    path = Path(__file__).resolve().parent / "assets" / "nutrition.json"
    return tuple(sorted((x["name"] for x in json.loads(path.read_text(encoding="utf-8"))), key=len, reverse=True))


def phrase(text):
    """'김치찌개 먹고 싶어' → '김치찌개'"""
    m = re.search(r"([가-힣A-Za-z ]{2,24}?)\s*(?:이|가|을|를|은|는)?\s*(?:먹고\s*싶|해\s*먹|만들어|만들|먹을|요리|해\s*줘|해줘|어때)", text)
    if not m:
        return ""
    words = [w for w in m[1].split() if w not in STOP]
    return " ".join(words).strip()


def matches(text, meals):
    """원하는 메뉴에 맞는 레시피 제목 목록, 읽은 단서, 가벼운 메뉴 선호 여부."""
    p = phrase(text)
    titles = list(meals)
    hits, cue = [], ""
    # 1) 문구가 제목에 들어 있거나 문구의 단어가 모두 제목에 있음
    if p:
        words = p.split()
        hits = [t for t in titles if p.replace(" ", "") in t.replace(" ", "") or all(w in t for w in words)]
        cue = p if hits else ""
    # 2) 종류 단어
    if not hits:
        for word, rule in CATEGORIES.items():
            if word in text:
                hits = [
                    t for t in titles
                    if rule.get("ing", set()) & set(meals[t]["grams"])
                    or any(x in t for x in rule.get("title", ()))
                    or any(t.endswith(x) for x in rule.get("title_end", ()))
                ]
                if hits:
                    cue = word
                    break
    # 3) 재료 이름 ("두부로 뭐 해 먹지")
    if not hits:
        for name in ingredient_names():
            if name in text:
                hits = [t for t in titles if name in meals[t]["grams"]]
                if hits:
                    cue = name
                    break
    return hits, cue or p, any(w in text for w in LIGHT), p


def shopping_item(text):
    """'두부 사고 싶어' → '두부'. 재료 이름이 없으면 None."""
    if not re.search(r"(사고\s*싶|사야|살래|살까|구매|주문|장보|사 줘|사줘)", text):
        return None
    if re.search(r"(먹고\s*싶|해\s*먹|만들|요리|레시피)", text):  # 메뉴를 말하면 장보기가 아니라 메뉴 요청
        return None
    return next((n for n in ingredient_names() if n in text), None)
