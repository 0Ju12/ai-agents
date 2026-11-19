from collections import Counter
from datetime import date
import re
from uuid import uuid4
from urllib.parse import quote
from .catalog import ALLERGENS, ANIMAL, SUBSTITUTES, canonical, nutrient_totals
from .training import routine


def add_lot(state, item, quantity=None, unit="g", expires=None):
    item = canonical(item)
    if not item or len(item) > 50:
        raise ValueError("재료 이름을 1~50자로 입력하세요.")
    if expires:
        expires = date.fromisoformat(expires).isoformat()
    if quantity is not None:
        if unit == "개" and item != "달걀":
            raise ValueError("이 재료는 포장에 표시된 g 수를 입력하세요.")
        if unit not in {"g", "kg", "개"}:
            raise ValueError("g, kg 또는 달걀 개수를 입력하세요.")
        quantity = round(float(quantity) * {"g": 1, "kg": 1000, "개": 50}[unit], 2)
        if not 0 < quantity <= 100000:
            raise ValueError("한 포장의 중량은 0~100kg 범위에서 입력하세요.")
    elif not expires and any(
        x["item"] == item and x["grams"] is None and not x["expires"] for x in state["lots"]
    ):
        return
    state["lots"].append({"id": uuid4().hex, "item": item, "grams": quantity, "expires": expires})


def add_text(state, fields):
    for text in fields:
        match = re.fullmatch(
            r"(.+?)\s+(\d+(?:\.\d+)?)\s*(g|kg|개)(?:\s+(\d{4}-\d{2}-\d{2}))?", text.strip()
        )
        if match:
            add_lot(state, match[1], match[2], match[3], match[4])
        else:
            add_lot(state, text)


def inventory(state, day):
    available = {}
    for lot in state["lots"]:
        if lot["expires"] and lot["expires"] < day:
            continue
        row = available.setdefault(lot["item"], {"grams": 0, "unknown": False, "earliest": None})
        if lot["grams"] is None:
            row["unknown"] = True
        else:
            row["grams"] += lot["grams"]
        if lot["expires"] and (not row["earliest"] or row["earliest"] > lot["expires"]):
            row["earliest"] = lot["expires"]
    return available


def shortages(grams, available, servings=1):
    missing, unchecked = {}, []
    for item, g in grams.items():
        supply = available.get(item, {})
        remaining = round(g * servings - supply.get("grams", 0), 2)
        if remaining <= 0:
            continue
        if supply.get("unknown"):
            unchecked.append(item)
        else:
            missing[item] = remaining
    return missing, unchecked


def cooking_time(state, meal):
    times = [x["actual"] for x in state.get("records", []) if x["meal"] == meal["title"]]
    return round(sum(times[-5:]) / len(times[-5:])) if times else meal["minutes"]


def excluded_by_food(state, grams):
    avoid = set(state.get("avoid", []))
    for name in grams:
        if avoid & ({name} | ALLERGENS.get(name, set())):
            return "제외 식재료 · " + name
        if state.get("diet") == "식물성" and name in ANIMAL:
            return "식물성 조건 · " + name
    return None


def select_meal(state, meals, refs, day, available_minutes=None):
    available = inventory(state, day)
    limit = state["minutes"] if available_minutes is None else min(state["minutes"], available_minutes)
    choices = []
    excluded = []
    for key, meal in meals.items():
        wanted = state.get("wanted")
        if wanted and wanted != key:
            continue
        title = key
        grams = dict(meal["grams"])
        steps = list(meal["steps"])
        for item, replacement in state.get("swaps", {}).items():
            if (
                item in grams
                and item not in available
                and replacement in available
                and replacement in SUBSTITUTES.get(item, set())
            ):
                grams[replacement] = grams.get(replacement, 0) + grams.pop(item)
                title = title.replace(item, replacement)
                steps = [s.replace(item, replacement) for s in steps]
        minutes = cooking_time(state, {**meal, "title": title})
        reason = excluded_by_food(state, grams)
        if minutes is None and not reason:
            reason = "조리시간 미확인"
        if minutes is not None and minutes > limit and not reason:
            reason = f"조리 {minutes}분 > 가용 {limit}분"
        if reason:
            excluded.append({"메뉴": title, "사유": reason})
            continue
        missing, unchecked = shortages(grams, available)
        facts = nutrient_totals(grams, refs)
        priority = state.get("priority")
        expiry = min(
            (available[k]["earliest"] for k in grams if k in available and available[k]["earliest"]),
            default="9999-12-31",
        )
        rank = (
            len(missing),
            bool(priority and priority not in grams),
            expiry,
            -(facts.get("protein_g") or 0) if state.get("diet") == "단백질 우선" else 0,
            -len(grams.keys() & available.keys()),
            minutes,
            title,
        )
        choices.append((rank, title, grams, steps, minutes, missing, unchecked, facts, meal["source"]))
    if not choices:
        return {
            "안내": "조건에 맞는 메뉴가 없습니다. 시간 또는 메뉴 조건을 확인하세요.",
            "제외 후보": excluded,
        }
    choices.sort(key=lambda x: x[0])
    _, title, grams, steps, minutes, missing, unchecked, facts, source = choices[0]
    for other in choices[1:4]:
        excluded.append(
            {"메뉴": other[1], "사유": f"부족 재료 {len(other[5])}종 · {other[4]}분, 우선순위 다음"}
        )
    return {
        "메뉴": title,
        "상태": "추가 구매 필요" if missing else "재료 보유",
        "부족분": sorted(missing),
        "부족량(g)": missing,
        "수량 확인": unchecked,
        "조리시간(분)": minutes,
        "예시 1인분(g)": grams,
        "조리 단계": steps,
        "조리법": " ".join(steps),
        "예상 kcal": round(facts["kcal"]) if facts["kcal"] is not None else None,
        "영양": facts,
        "근거": source,
        "영양 출처": [
            {"재료": x, "url": "https://fdc.nal.usda.gov/food-details/" + str(refs[x]["fdc_id"])}
            for x in grams
            if x in refs
        ],
        "판단 기준": f"가용 {limit}분 · 조리 {minutes}분 · 부족 {len(missing)}종 · 수량 미확인 {len(unchecked)}종",
        "제외 후보": excluded,
        "쿠팡": {x: "https://www.coupang.com/np/search?q=" + quote(x) for x in missing},
        "네이버": {x: "https://search.shopping.naver.com/search/all?query=" + quote(x) for x in missing},
        "유튜브": "https://www.youtube.com/results?search_query=" + quote(title + " 레시피"),
        "인스타그램": "https://www.instagram.com/explore/tags/" + quote(title.replace(" ", "")) + "/",
    }


def cook(state, servings, actual, day):
    plan = state.get("last_meal", {})
    if not plan.get("예시 1인분(g)"):
        raise ValueError("조리할 메뉴를 먼저 선택하세요.")
    if not 1 <= servings <= 20 or not 1 <= actual <= 600:
        raise ValueError("조리 분량이나 시간을 확인하세요.")
    grams = plan["예시 1인분(g)"]
    if excluded_by_food(state, grams):
        raise ValueError("제외 재료 조건이 바뀌었습니다. 메뉴를 다시 선택하세요.")
    # 냉장고에 없던 재료로도 요리할 수 있다(따로 산 재료 등): 있는 만큼만 차감하고 없던 재료는 기록에 남긴다
    missing, unchecked = shortages(grams, inventory(state, day), servings)
    for item, weight in grams.items():
        needed = weight * servings
        lots = sorted(
            (
                x
                for x in state["lots"]
                if x["item"] == item
                and (not x["expires"] or x["expires"] >= day)
                and x["grams"] is not None
            ),
            key=lambda l: l["expires"] or "9999-12-31",
        )
        for lot in lots:
            take = min(needed, lot["grams"])
            lot["grams"] = round(lot["grams"] - take, 2)
            needed -= take
            if needed <= 0:
                break
    state["lots"] = [x for x in state["lots"] if x["grams"] is None or x["grams"] > 0]
    state["batches"].append(
        {
            "id": uuid4().hex,
            "title": plan["메뉴"],
            "servings": servings,
            "facts": {"nutrients": plan.get("영양", {}), "ingredients": list(grams), "cooked": day},
        }
    )
    state["records"].append(
        {
            "meal": plan["메뉴"],
            "actual": actual,
            "planned": plan["조리시간(분)"],
            "servings": servings,
            "date": day,
            "미계량": unchecked,
            "냉장고에 없던 재료": missing,
        }
    )
    return missing


def leftovers(state):
    counts = Counter()
    for batch in state["batches"]:
        counts[batch["title"]] += batch["servings"]
    return dict(counts)


def eat(state, title, daily):
    batch = next((b for b in state["batches"] if b["title"] == title), None)
    if not batch:
        raise ValueError("먹을 수 있는 조리 기록을 선택하세요.")
    if excluded_by_food(state, batch["facts"].get("ingredients", [])):
        raise ValueError("제외 재료가 포함된 음식입니다.")
    daily.setdefault("eaten", []).append(title)
    daily.setdefault("intake", []).append(
        {"title": title, "nutrients": batch["facts"].get("nutrients", {})}
    )
    batch["servings"] -= 1
    if not batch["servings"]:
        state["batches"].remove(batch)


def suggest(state, meals, refs, day, limit=None):
    available = state["minutes"] if limit is None else min(limit, state["minutes"])
    if state.get("view_wanted") and state.get("wanted"):
        plan = select_meal(state, meals, refs, day, available)
    elif state.get("out_date") == day:
        plan = {"안내": "오늘은 외식 · 재료 보존"}
    elif any(not excluded_by_food(state, b["facts"].get("ingredients", [])) for b in state["batches"]):
        safe = [
            b for b in state["batches"] if not excluded_by_food(state, b["facts"].get("ingredients", []))
        ]
        plan = {"남은 음식 우선": leftovers({"batches": safe}), "판단 기준": "조리 완료된 식사 우선"}
    elif state["lots"] or state.get("wanted"):
        plan = select_meal(state, meals, refs, day, available)
    else:
        plan = {"안내": "재료를 등록하면 오늘의 식사를 추천합니다."}
    exercise = routine(state, available - plan.get("조리시간(분)", 0))
    plan.update({"운동": exercise["summary"], "루틴": exercise})
    return plan
