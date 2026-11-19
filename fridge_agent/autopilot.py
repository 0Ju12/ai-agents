"""상황을 말하면 Agent 가 이어서 진행하는 일들 (자동 진행).

    "퇴근했는데 20분밖에 없어. 단백질 위주로 먹고 싶어"
      → 조건 반영(시간·식단) → 추천 후보 3개와 근거 → 1순위 메뉴 확정
      → 부족 재료 장바구니 담기 → 조리 영상·인기 게시물 찾기 → 조리 모드 준비

원칙
- 무엇을 할지는 규칙이 기본안을 만들고, 모델(있으면)이 '할 일 목록과 인분'만 고른다.
  모델이 고를 수 있는 작업은 아래 ACTIONS 뿐이고, 실행 조건(부족 재료가 있는지 등)은 코드가 다시 확인한다.
- 재고·분량·시간 판단은 모두 기존 도메인 코드(select_meal, add_shortages)가 한다.
- 실행한 일은 '자동 진행' 목록으로 돌려주고, 되돌리는 명령을 함께 준다.
"""

import os
import re
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

import gateway
from domain.kitchen import add_lot, inventory, select_meal
from domain.shopping import add_shortages

ACTIONS = ("메뉴확정", "장바구니", "영상", "조리모드")
BUY_WORDS = ("사야", "장보", "구매", "주문", "없으면", "사줘", "담아")
NO_BUY_WORDS = ("사지 말", "장보기 말", "구매 말", "있는 걸로만", "있는 재료로만", "있는 것만")

# 예시 냉장고: 소비기한이 제각각이라 '임박 재료부터' 추천이 드러나게 했다 (오늘 기준 상대 날짜).
DEMO_LOTS = [
    ("두부", 300, 1), ("달걀", 500, 9), ("대파", 80, 3), ("양파", 400, 14), ("김치", 600, 25),
    ("밥", 420, 2), ("플레인요거트", 450, 4), ("바나나", 240, 2), ("시금치", 150, 2), ("닭가슴살", 200, 3),
    ("토마토", 300, 5), ("오이", 140, 6), ("식용유", 500, 180), ("간장", 500, 300), ("참기름", 160, 200),
    ("오트밀", 400, 120), ("감자", 450, 20), ("당근", 200, 12), ("마늘", 80, 10), ("설탕", 500, 365), ("깨", 100, 180),
]


def seed_demo(state, day):
    """예시 재료로 냉장고를 다시 채운다(기존 포장·장바구니는 비운다)."""
    base = date.fromisoformat(day)
    state["lots"], state["cart"] = [], {}
    for name, grams, days in DEMO_LOTS:
        add_lot(state, name, grams, "g", (base + timedelta(days=days)).isoformat())
    state["demo_seeded"] = True


def ranked(state, meals, refs, day, limit=None, top=3, light=False):
    """조건을 통과한 메뉴를 select_meal 과 같은 기준으로 줄 세우고, 사람이 읽을 근거를 붙인다."""
    available = inventory(state, day)
    out = []
    for title in meals:
        plan = select_meal({**state, "wanted": title}, meals, refs, day, limit)
        if not plan.get("메뉴"):
            continue
        used = [k for k in plan["예시 1인분(g)"] if k in available]
        soon = sorted(
            ((k, (date.fromisoformat(available[k]["earliest"]) - date.fromisoformat(day)).days) for k in used if available[k].get("earliest")),
            key=lambda x: x[1],
        )
        reasons = []
        if soon and soon[0][1] <= 3:
            reasons.append(f"기한 임박 {soon[0][0]} D-{soon[0][1]}" if soon[0][1] > 0 else f"{soon[0][0]} 오늘까지")
        reasons.append("재료 모두 보유" if not plan["부족분"] else f"부족 {len(plan['부족분'])}종({', '.join(plan['부족분'])})")
        reasons.append(f"조리 {plan['조리시간(분)']}분")
        protein = plan["영양"].get("protein_g")
        if protein is not None:
            reasons.append(f"단백질 {protein:g}g")
        kcal = plan["예상 kcal"]
        focus = set(state.get("health_focus", []))
        heavy = light or "weight" in focus or state.get("goal") == "체중 관리"
        if heavy and kcal is not None:
            reasons.insert(0, f"{kcal}kcal")
        nut = plan["영양"]
        health_key = 0
        for name, field, unit in (("sodium", "sodium_mg", "mg"), ("sugar", "carb_g", "g"), ("fat", "fat_g", "g")):
            if name in focus and nut.get(field) is not None:
                health_key += nut[field] / {"sodium_mg": 2000, "carb_g": 130, "fat_g": 50}[field]  # 하루 기준량 대비 비율 합
                reasons.append({"sodium": "나트륨", "sugar": "탄수화물", "fat": "지방"}[name] + f" {nut[field]:g}{unit}")
        key = (
            len(plan["부족분"]),
            round(health_key, 3),
            (kcal if kcal is not None else 9999) if heavy else 0,
            soon[0][1] if soon else 999,
            -(protein or 0) if state.get("diet") == "단백질 우선" else 0,
            plan["조리시간(분)"],
        )
        out.append((key, {"메뉴": plan["메뉴"], "근거": reasons, "부족분": plan["부족분"], "조리시간(분)": plan["조리시간(분)"], "예상 kcal": plan["예상 kcal"], "단백질(g)": protein}))
    out.sort(key=lambda x: x[0])
    return [x[1] for x in out[:top]]


class AutoPlan(BaseModel):
    actions: list[Literal["메뉴확정", "장바구니", "영상", "조리모드"]] = Field(default_factory=list, max_length=4)
    servings: int = Field(default=1, ge=1, le=6, description="사용자가 말한 인원·인분. 말하지 않았으면 1")
    reason: str = Field(default="", max_length=160)
    message: str = Field(default="", max_length=400, description="사용자에게 보여 줄 2~3문장. top 의 메뉴·근거 값만 쓰고 숫자를 새로 만들지 않는다. 마크다운 금지")


PROMPT = (
    "사용자의 상황 문장을 보고 이어서 진행할 작업을 고른다. 메뉴확정(1순위 메뉴로 정하기), 장바구니(부족 재료 담기), "
    "영상(조리 영상·인기 게시물 찾기), 조리모드(단계별 안내 준비) 중에서만 고른다. "
    "사지 말라고 하면 장바구니를 빼고, 인원이 나오면 servings 로 적는다. 재고·영양 숫자를 새로 만들지 않는다. "
    "message 에는 top 메뉴를 고른 이유를 top 의 근거로 2~3문장 평문으로 쓴다."
)


def servings_in(text):
    m = re.search(r"(\d{1,2})\s*(?:인분|명|사람)", text)
    if m and 1 <= int(m[1]) <= 6:
        return int(m[1])
    return {"둘이": 2, "셋이": 3, "넷이": 4, "혼자": 1}.get(next((w for w in ("둘이", "셋이", "넷이", "혼자") if w in text), ""), 1)


def decide(message, top, emit):
    """규칙 기본안 → 모델 보충(선택) → 코드 검증."""
    # 장바구니는 인분까지 곱해 실제로 부족할 때만 담긴다(run 에서 다시 계산)
    actions = ["메뉴확정", "영상", "조리모드"]
    if top and not any(w in message for w in NO_BUY_WORDS):
        actions.insert(1, "장바구니")
    servings, how, reason, said = servings_in(message), "규칙", "상황 문장에서 시간·식단·인원을 반영하고 1순위 메뉴로 진행", ""
    if os.getenv("AUTOPILOT_LLM", "1") == "1" and gateway.configured():
        try:
            plan = gateway.structured("자동 진행", PROMPT, {"message": message, "top": top}, AutoPlan)
            actions = [a for a in ACTIONS if a in plan.actions] or actions
            servings, how, reason = plan.servings, "모델(코드 검증)", plan.reason or reason
            said = re.sub(r"[*#`]+", "", plan.message).strip()
            emit("llm_decision", "자동 진행", method="model", decision=actions, reason=reason[:160])
        except (ValueError, OSError):
            emit("error", "자동 진행", reason="규칙 기본안 사용")
    if not top:
        actions = []
    if any(w in message for w in NO_BUY_WORDS) and "장바구니" in actions:
        actions.remove("장바구니")
    return actions, servings, how, reason, said


def options(pool, shown=(), kr=()):
    """선택지 묶음: 바로 가능 · 1~2개만 사면 가능 · 국내 레시피. 이미 보여 준 메뉴는 뺀다."""
    fresh = [x for x in pool if x["메뉴"] not in shown]
    return {
        "바로 가능": [x for x in fresh if not x["부족분"]][:4],
        "조금만 사면": [x for x in fresh if 1 <= len(x["부족분"]) <= 2][:3],
        "국내 레시피": [x for x in kr if x["메뉴"] not in shown][:4],
    }


def run(state, message, meals, refs, day, emit, limit=None, media=None, named=None, more=False, kr=None, wanted=None):
    """자동 진행을 실행하고 결과 묶음을 돌려준다. media(menu) 는 영상 조회, kr() 은 국내 레시피 후보 조회 함수."""
    emit("node_start", "자동 진행")
    hits, cue, light, said_menu = wanted or ([], "", False, "")
    pool = ranked(state, meals, refs, day, limit, top=len(meals), light=light)
    if hits:  # 말한 메뉴·종류에 맞는 레시피를 앞으로 (그 안에서는 원래 순서 유지)
        inside = {x["메뉴"] for x in pool}
        if limit is not None or state.get("minutes"):
            # 콕 집어 말한 메뉴는 가용 시간을 넘어도 후보로 보여 주고, 넘는 시간을 근거에 적는다
            wide = {**state, "minutes": 240}
            for x in ranked(wide, {t: meals[t] for t in hits if t not in inside}, refs, day, None, top=len(hits), light=light):
                over = x["조리시간(분)"] - min(state["minutes"], limit or state["minutes"])
                x["근거"].insert(0, f"가용 시간보다 {over}분 더 걸려요")
                x["시간 초과"] = over
                pool.append(x)
        pool.sort(key=lambda x: (x["메뉴"] not in hits, x.get("시간 초과", 0) > 0 and x["메뉴"] not in hits))
    if named:  # 사용자가 메뉴 이름을 그대로 말했으면 그 메뉴를 1순위로
        pool.sort(key=lambda x: x["메뉴"] != named)
    missed = said_menu if said_menu and not hits and not named else ""
    shown = state.get("shown_picks", []) if more else []
    pool = [x for x in pool if x["메뉴"] not in shown] if more else pool
    kr_rows = kr() if kr else []
    choice = options(pool, shown, kr_rows)
    top3 = pool[:3]
    top = top3[0] if top3 else None
    if more:  # "다른 후보" 요청: 후보만 새로 보여 주고 다른 작업은 하지 않는다 (모델 호출 없음)
        actions, servings, how, reason, said = [], 1, "규칙", "이미 보여 드린 후보를 빼고 다음 후보를 골랐어요", ""
    else:
        actions, servings, how, reason, said = decide(message, top, emit)
    listed = [x["메뉴"] for group in choice.values() for x in group] + [x["메뉴"] for x in top3]
    state["shown_picks"] = list(dict.fromkeys((shown if more else []) + listed))[-60:]
    done = []
    if top and top.get("시간 초과", 0) > 0 and "메뉴확정" in actions:
        # 콕 집어 말한 메뉴가 가용 시간을 넘으면 시간을 늘리고, 되돌릴 수 있게 알린다
        old = state["minutes"]
        state["minutes"] = top["조리시간(분)"]
        done.append({"작업": "가용 시간 조정", "결과": f"{old}분 → {state['minutes']}분 ({top['메뉴']} 조리 시간)", "되돌리기": f"시간 {old}"})
        limit = None
    if "메뉴확정" in actions:
        state["wanted"], state["view_wanted"] = top["메뉴"], True
        done.append({"작업": "메뉴 확정", "결과": f"{top['메뉴']} · {', '.join(top['근거'])}", "되돌리기": "메뉴 자동"})
    if "장바구니" in actions:
        # 자동으로 담았던 다른 메뉴의 재료는 빼고(직접 담은 것은 유지) 이번 메뉴의 부족분만 담는다
        cart = state.setdefault("cart", {})
        for name in [k for k, v in cart.items() if v.get("auto") and v.get("meal") != top["메뉴"]]:
            del cart[name]
        plan = select_meal({**state, "wanted": top["메뉴"]}, meals, refs, day, limit)
        missing, _ = add_shortages(state, plan, servings)
        for name in missing:
            cart[name]["auto"] = True
        if missing:
            items = ", ".join(f"{k} {v:g}g" for k, v in missing.items())
            done.append({"작업": "장바구니 담기", "결과": f"{servings}인분 기준 {items}", "되돌리기": [f"장바구니삭제 {k}" for k in missing]})
            emit("auto_action", "장바구니", items=list(missing))
    found = None
    if "영상" in actions and media:
        found = media(top["메뉴"])
        yt, ig = found["youtube"], found["instagram"]
        n = (len(yt["data"]) if yt.get("ok") else 0) + (len(ig["data"]) if ig.get("ok") else 0)
        done.append({"작업": "영상·게시물 찾기", "결과": f"{n}건" if n else "키가 없어 직접 링크를 붙이면 화면에서 재생돼요", "되돌리기": None})
    if "조리모드" in actions and top:
        done.append({"작업": "조리 모드 준비", "결과": f"{top['메뉴']} {servings}인분 단계 안내", "되돌리기": None})
    emit("node_end", "자동 진행")
    return {
        "자동 진행": done,
        "추천 후보": top3,
        "선택지": choice,
        "더보기": more,
        "확정 메뉴": top["메뉴"] if top and "메뉴확정" in actions else None,
        "인분": servings,
        "판단 방법": how,
        "판단 이유": (f"‘{cue}’에 맞는 레시피에서 골랐어요. " if hits else "") + (f"‘{missed}’ 레시피는 아직 없어 지금 재료로 가능한 메뉴를 골랐어요. " if missed else "") + ("열량이 낮은 순으로 골랐어요. " if light else "") + reason,
        "메시지": said,
        "영상": found,
        "조리 모드": {"title": top["메뉴"], "servings": servings} if top and "조리모드" in actions else None,
    }


# ── 사용자가 붙인 영상 링크 (키 없이도 화면 안에서 재생) ─────────────
YT = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})")
IG = re.compile(r"^https://(?:www\.)?instagram\.com/(p|reel|reels)/([\w-]{5,40})/?")


def parse_link(url):
    url = (url or "").strip()
    if not url.startswith("https://"):
        return None
    m = YT.search(url)
    if m and re.match(r"^https://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/", url):
        return {"type": "youtube", "id": m[1], "url": "https://www.youtube.com/watch?v=" + m[1]}
    m = IG.match(url)
    if m:
        kind = "reel" if m[1].startswith("reel") else "p"
        return {"type": "instagram", "url": f"https://www.instagram.com/{kind}/{m[2]}/"}
    return None


def add_link(state, menu, url):
    menu = (menu or "").strip()
    link = parse_link(url)
    if not 1 <= len(menu) <= 40 or not link:
        raise ValueError("YouTube 또는 Instagram 게시물 주소(https://)를 붙여 넣으세요.")
    links = state.setdefault("media_links", {}).setdefault(menu, [])
    if link not in links:
        links.insert(0, link)
    del links[8:]
    return link


def merge_links(found, links, steps_count):
    """API 결과 앞에 사용자가 붙인 링크를 넣는다. 키가 없어도 링크가 있으면 ok."""
    yt_links = [x for x in links if x["type"] == "youtube"]
    ig_links = [x for x in links if x["type"] == "instagram"]
    if yt_links:
        mine = [{"id": x["id"], "title": "내가 추가한 영상", "channel": "직접 추가", "url": x["url"], "chapters": [], "step_starts": [None] * steps_count, "matching": "직접 추가"} for x in yt_links]
        yt = found["youtube"]
        found["youtube"] = {"ok": True, "data": mine + (yt["data"] if yt.get("ok") else []), "source": "직접 추가한 링크" + (" · " + yt["source"] if yt.get("ok") else "")}
    if ig_links:
        mine = [{"title": "내가 추가한 게시물", "url": x["url"]} for x in ig_links]
        ig = found["instagram"]
        found["instagram"] = {"ok": True, "data": mine + (ig["data"] if ig.get("ok") else []), "source": "직접 추가한 링크" + (" · " + ig["source"] if ig.get("ok") else "")}
    return found
