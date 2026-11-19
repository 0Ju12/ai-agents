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


class Seen(BaseModel):
    name: str = Field(max_length=40, description="한국어 음식 또는 재료 이름")
    grams: float | None = Field(default=None, ge=1, le=3000, description="보이는 양의 대략적인 g. 모르면 null")
    count: int | None = Field(default=None, ge=1, le=99, description="포장·개수. 모르면 null")
    confidence: float = Field(default=0.5, ge=0, le=1)


class Sight(BaseModel):
    items: list[Seen] = Field(default_factory=list, max_length=15)
    note: str = Field(default="", max_length=120, description="사진이 흐리거나 판단이 어려운 이유. 없으면 빈 문자열")


PROMPTS = {
    "meal": "식사 사진에 보이는 음식을 한국어 이름으로 나열하고 1인분 기준 대략적인 g 을 적는다. 열량은 쓰지 않는다. 확실하지 않으면 confidence 를 낮춘다.",
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


def nutrition(items, refs):
    """확인된 [{name, grams}] 의 영양 합계. 참조가 없는 재료가 하나라도 있으면 그 항목은 None."""
    known = {canonical(x["name"]): x["grams"] for x in items if x.get("grams")}
    rows = [
        {
            "이름": name,
            "분량(g)": g,
            "참조": refs[name].get("reference_food") if name in refs else None,
            "영양": nutrient_totals({name: g}, refs) if name in refs else None,
        }
        for name, g in known.items()
    ]
    return {
        "항목": rows,
        "합계": nutrient_totals(known, refs) if known else None,
        "미확인": [r["이름"] for r in rows if r["영양"] is None],
        "출처": "USDA FoodData Central 100g 참조값을 확인한 중량에 맞춰 환산",
    }


def analyze(kind, image, refs, stock=(), emit=None):
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
            }
        )
    emit("tool_result", "vision", ok=True, count=len(items))
    out = {"ok": True, "kind": kind, "후보": items, "메모": sight.note, "안내": "후보입니다. 이름과 양을 확인한 뒤 저장하세요."}
    if kind == "meal":
        out["예상 영양"] = nutrition([x for x in items if x["grams"]], refs)
    return out
