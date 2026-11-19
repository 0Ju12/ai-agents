"""사진 기록: 식사 사진 → 음식 후보, 냉장고·장바구니 사진 → 재료 후보.

- 모델은 '후보'만 낸다. 사용자가 이름과 g 을 확인해야 기록된다.
- 열량·단백질은 사진에서 추정하지 않는다. 확인된 이름 × g 에 공공 영양 참조(100g 기준)를 곱한다.
- 사진은 저장하지 않는다. 형식·크기를 검사한 뒤 모델 호출에만 쓴다 (NF3001·NF3002).
"""

import base64
import binascii
import re

from pydantic import BaseModel, Field

import gateway
from domain.catalog import canonical, nutrient_totals

MAX_BYTES = 5_000_000
DATA_URL = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)$")


class Part(BaseModel):
    name: str = Field(max_length=40, description="주재료 한국어 이름")
    grams: float = Field(ge=1, le=2000, description="그 재료의 대략적인 g")


class Seen(BaseModel):
    name: str = Field(max_length=40, description="한국어 음식 또는 재료 이름")
    grams: float | None = Field(default=None, ge=1, le=3000, description="보이는 양의 대략적인 g. 모르면 null")
    count: int | None = Field(default=None, ge=1, le=99, description="포장·개수. 모르면 null")
    confidence: float = Field(default=0.5, ge=0, le=1)
    parts: list[Part] = Field(default_factory=list, max_length=10, description="요리면 주재료와 대략적인 g. 재료 자체면 비워 둔다")


class Sight(BaseModel):
    items: list[Seen] = Field(default_factory=list, max_length=15)
    note: str = Field(default="", max_length=120, description="사진이 흐리거나 판단이 어려운 이유. 없으면 빈 문자열")


PROMPTS = {
    "meal": "식사 사진에 보이는 음식을 한국어 이름(예: 김치찌개, 두부조림, 밥)으로 나열하고 1인분 기준 대략적인 g 을 적는다. 요리면 parts 에 주재료와 대략적인 g 을 적는다. 열량은 쓰지 않는다. 확실하지 않으면 confidence 를 낮춘다.",
    "fridge": "냉장고·장바구니 사진에 보이는 식재료를 한국어 기본 이름(예: 달걀, 두부, 양파)으로 나열하고 보이는 개수를 적는다. 브랜드·가격은 쓰지 않는다.",
}


def decode(image):
    """data URL 을 검사한다. 통과하면 그대로 돌려주고, 아니면 ValueError."""
    m = DATA_URL.match(image or "")
    if not m:
        raise ValueError("JPEG·PNG·WEBP 사진을 선택하세요.")
    try:
        raw = base64.b64decode(re.sub(r"\s", "", m[2]), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("사진 파일을 읽지 못했어요.") from exc
    if not 100 <= len(raw) <= MAX_BYTES:
        raise ValueError("사진은 5MB 이하로 올려 주세요.")
    signatures = {"jpeg": b"\xff\xd8", "png": b"\x89PNG", "webp": b"RIFF"}
    if not raw.startswith(signatures[m[1]]):
        raise ValueError("사진 형식이 파일 내용과 다릅니다.")
    return image


def resolve(name, grams, refs, meals=None, parts=()):
    """음식 하나의 영양: ① 한끼 레시피(1인분 재료 × 먹은 g 비율) ② 재료 자체(USDA 100g) ③ 모델이 추정한 주재료 ④ 미확인."""
    name = canonical(name)
    meals = meals or {}
    key = name.replace(" ", "")
    title = name if name in meals else None
    if not title and name in refs and grams:  # 재료 자체("달걀", "밥")는 레시피보다 재료 참조를 먼저 쓴다
        return {"영양": nutrient_totals({name: grams}, refs), "근거": f"USDA 참조 · {refs[name].get('reference_food')}", "레시피": None}
    if not title and len(key) >= 2:
        # 요리 이름이 레시피 이름의 끝과 같으면 같은 요리로 본다: '김치찌개' ↔ '돼지고기 김치찌개'
        title = next((t for t in sorted(meals, key=len) if t.replace(" ", "").endswith(key) or key.endswith(t.replace(" ", ""))), None)
    if title:
        recipe = meals[title]["grams"]
        # 국·찌개처럼 물이 들어가는 요리는 단계에 적힌 물(mL≈g)까지 1인분 무게로 친다
        water = sum(int(m) for step in meals[title].get("steps", []) for m in re.findall(r"물\s*(\d{2,4})\s*mL", step))
        total = (sum(recipe.values()) + water) or 1
        factor = (grams / total) if grams else 1
        scaled = {k: v * factor for k, v in recipe.items()}
        facts = nutrient_totals(scaled, refs)
        return {"영양": facts, "근거": f"한끼 레시피 ‘{title}’ 재료 기준 ({round(factor, 2)}인분)", "레시피": title}
    if name in refs and grams:
        return {"영양": nutrient_totals({name: grams}, refs), "근거": f"USDA 참조 · {refs[name].get('reference_food')}", "레시피": None}
    usable = {canonical(p["name"]): p["grams"] for p in parts if canonical(p["name"]) in refs}
    if usable:
        facts = nutrient_totals(usable, refs)
        missed = [p["name"] for p in parts if canonical(p["name"]) not in refs]
        return {"영양": facts, "근거": "사진에서 추정한 주재료 " + ", ".join(f"{k} {v:g}g" for k, v in usable.items()) + (f" (참조 없는 재료 {', '.join(missed)} 제외)" if missed else ""), "레시피": None}
    return {"영양": None, "근거": "영양 참조를 찾지 못했어요", "레시피": None}


def nutrition(items, refs, meals=None):
    """확인된 [{name, grams, parts?}] 의 음식별 영양과 합계. 모르는 음식은 합계에서 빼고 '미확인'으로 알린다."""
    rows = []
    for x in items:
        if not x.get("grams"):
            continue
        r = resolve(x["name"], x["grams"], refs, meals, x.get("parts", []))
        rows.append({"이름": canonical(x["name"]), "분량(g)": x["grams"], **r})
    known = [r["영양"] for r in rows if r["영양"]]
    total = {k: round(sum(f.get(k) or 0 for f in known), 1) for k in ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g", "sodium_mg")} if known else None
    return {
        "항목": rows,
        "합계": total,
        "미확인": [r["이름"] for r in rows if r["영양"] is None],
        "출처": "한끼 레시피·USDA FoodData Central 100g 참조값을 확인한 중량에 맞춰 환산",
    }


def analyze(kind, image, refs, stock=(), emit=None, meals=None):
    emit = emit or (lambda *a, **k: None)
    if kind not in PROMPTS:
        raise ValueError("사진 종류를 확인하세요.")
    decode(image)
    if not gateway.configured():
        return {"ok": False, "error": "MISSING_KEY", "setting": "GMS_KEY", "안내": "모델 키가 없어 사진을 분석할 수 없어요. 직접 입력해 주세요."}
    emit("tool_call", "vision", argument=kind)
    try:
        sight = gateway.see("사진 " + kind, PROMPTS[kind], image, Sight)
    except (ValueError, OSError):
        emit("tool_result", "vision", ok=False, error="SOURCE_UNAVAILABLE")
        return {"ok": False, "error": "SOURCE_UNAVAILABLE", "안내": "사진 분석에 실패했어요. 직접 입력해 주세요."}
    have = {canonical(x) for x in stock}
    items, seen = [], set()
    for s in sight.items:
        name = canonical(s.name)
        if not name or name in seen:
            continue
        seen.add(name)
        items.append(
            {
                "name": name,
                "grams": s.grams,
                "count": s.count,
                "confidence": round(s.confidence, 2),
                "영양 참조": name in refs,
                "보유": name in have,
                "parts": [p.model_dump() for p in s.parts],
            }
        )
    emit("tool_result", "vision", ok=True, count=len(items))
    out = {"ok": True, "kind": kind, "후보": items, "메모": sight.note, "안내": "후보입니다. 이름과 양을 확인한 뒤 저장하세요."}
    if kind == "meal":
        out["예상 영양"] = nutrition([x for x in items if x["grams"]], refs, meals)
        basis = {r["이름"]: r for r in out["예상 영양"]["항목"]}
        for x in items:  # 후보마다 계산 근거와 예상 열량을 붙여 사용자가 확인할 수 있게 한다
            b = basis.get(x["name"])
            x["근거"] = b["근거"] if b else "양(g)을 넣으면 계산해요"
            x["예상 kcal"] = (b["영양"] or {}).get("kcal") if b else None
    return out
