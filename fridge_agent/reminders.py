"""물·영양제 알림.

- 물: '언제부터 언제까지, 몇 시간마다'로 정하고, 지금까지 마신 양이 하루 목표의 진도보다
  앞서 있으면 그 알림은 건너뛴다(코드 판정). 목표는 설정의 water_ml, 없으면 1,500mL 를 기본으로 쓴다.
- 영양제: 사용자가 적은 이름·복용량·시각만 쓴다. 복용량을 권하거나 바꾸지 않는다.
  오늘 이미 '먹었어요'를 누른 시각 알림은 건너뛴다.
- 알림을 보내는 쪽: 웹은 화면이 열려 있을 때 /api/reminders/due 를 1분마다 확인하고,
  Android 는 /api/reminders 의 일정을 받아 AlarmManager 로 앱이 꺼져 있어도 알린다.
"""

import re
from datetime import datetime
from uuid import uuid4

DEFAULT_WATER_ML = 1500
HHMM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
KINDS = {"water", "supplement"}
SUPPLEMENT_WORDS = ("영양제", "비타민", "오메가", "유산균", "마그네슘", "철분", "칼슘", "루테인", "아연", "밀크씨슬", "프로바이오틱스", "엽산")


def minutes(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def hhmm(total):
    return f"{total // 60:02d}:{total % 60:02d}"


def times_of(r):
    """알림 시각 목록. 물은 시작~끝을 간격으로 나눈다."""
    if r["kind"] == "water":
        start, end, step = minutes(r["start"]), minutes(r["end"]), r["every_min"]
        return [hhmm(t) for t in range(start, end + 1, step)]
    return list(r["times"])


def validate(params):
    kind = params.get("kind")
    if kind not in KINDS:
        raise ValueError("물 또는 영양제 알림을 선택하세요.")
    r = {"id": uuid4().hex[:10], "kind": kind, "enabled": True}
    if kind == "water":
        start, end = params.get("start", "09:00"), params.get("end", "21:00")
        every = int(params.get("every_min", 120))
        if not (HHMM.match(start) and HHMM.match(end)) or minutes(start) >= minutes(end) or not 30 <= every <= 360:
            raise ValueError("물 알림은 시작·끝 시각과 30~360분 간격으로 정하세요.")
        cup = int(params.get("cup_ml", 250))
        if not 50 <= cup <= 1000:
            raise ValueError("한 번에 마실 양은 50~1000mL 로 정하세요.")
        r.update({"title": "물 마시기", "start": start, "end": end, "every_min": every, "cup_ml": cup})
    else:
        name = str(params.get("name", "")).strip()
        dose = str(params.get("dose", "")).strip()
        times = sorted({str(t).strip() for t in params.get("times", [])})
        if not 1 <= len(name) <= 30 or len(dose) > 30 or not 1 <= len(times) <= 6 or not all(HHMM.match(t) for t in times):
            raise ValueError("영양제 이름(30자 이내)과 시각(최대 6개, HH:MM)을 확인하세요.")
        r.update({"title": name, "dose": dose, "times": times})
    return r


def add(state, params):
    r = validate(params)
    items = state.setdefault("reminders", [])
    if len(items) >= 20:
        raise ValueError("알림은 20개까지 만들 수 있어요.")
    if r["kind"] == "water":  # 물 알림은 하나만 둔다
        items[:] = [x for x in items if x["kind"] != "water"]
    items.append(r)
    return r


def find(state, rid):
    r = next((x for x in state.get("reminders", []) if x["id"] == rid), None)
    if not r:
        raise ValueError("알림을 찾지 못했어요.")
    return r


def remove(state, rid):
    find(state, rid)
    state["reminders"] = [x for x in state["reminders"] if x["id"] != rid]


def toggle(state, rid):
    r = find(state, rid)
    r["enabled"] = not r["enabled"]
    return r


def take(state, daily, rid, now):
    """영양제 '먹었어요' — 가장 가까운 지난 시각 슬롯에 기록한다."""
    r = find(state, rid)
    if r["kind"] != "supplement":
        raise ValueError("영양제 알림을 선택하세요.")
    past = [t for t in r["times"] if minutes(t) <= minutes(now) + 60] or r["times"][:1]
    slot = past[-1]
    log = daily.setdefault("supplements", [])
    if not any(x["id"] == rid and x["slot"] == slot for x in log):
        log.append({"id": rid, "name": r["title"], "dose": r.get("dose", ""), "slot": slot, "at": now})
    return slot


def water_target(state):
    return float(state.get("targets", {}).get("water_ml") or DEFAULT_WATER_ML)


def water_expected(r, target, now):
    """시작~끝 사이에 고르게 마신다고 볼 때 지금까지 마셨어야 할 양."""
    start, end, t = minutes(r["start"]), minutes(r["end"]), minutes(now)
    share = min(1.0, max(0.0, (t - start) / (end - start)))
    return round(target * share)


def due(state, daily, now, window_min=10):
    """지금(now, HH:MM) 기준 window_min 분 안에 지난 알림 중 보낼 것. 판정 근거를 함께 준다."""
    out, t = [], minutes(now)
    drank = daily.get("water_ml", 0) or 0
    taken = {(x["id"], x["slot"]) for x in daily.get("supplements", [])}
    for r in state.get("reminders", []):
        if not r["enabled"]:
            continue
        slots = [s for s in times_of(r) if 0 <= t - minutes(s) < window_min]
        if not slots:
            continue
        slot = slots[-1]
        if r["kind"] == "water":
            target = water_target(state)
            expected = water_expected(r, target, now)
            if drank >= target:
                continue
            if drank >= expected:  # 진도보다 앞서 있으면 건너뛴다
                continue
            out.append({
                "id": r["id"], "slot": slot, "kind": "water", "title": "물 마실 시간이에요",
                "body": f"오늘 {drank:g}mL 마셨어요. 목표 {target:g}mL 기준으로 지금쯤 {expected:g}mL 가 진도예요. 한 컵 {r['cup_ml']}mL 어때요?",
                "action": {"label": f"{r['cup_ml']}mL 마셨어요", "message": f"물 {r['cup_ml']}"},
            })
        else:
            if (r["id"], slot) in taken:
                continue
            out.append({
                "id": r["id"], "slot": slot, "kind": "supplement", "title": f"{r['title']} 드실 시간이에요",
                "body": (r.get("dose") + " · " if r.get("dose") else "") + "복용량은 제품 표시나 전문가 안내를 따르세요.",
                "action": {"label": "먹었어요", "message": "영양제복용 " + r["id"]},
            })
    return out


def overview(state, daily, now):
    """화면용: 오늘 알림 일정과 상태."""
    taken = {(x["id"], x["slot"]) for x in daily.get("supplements", [])}
    target = water_target(state)
    rows = []
    for r in state.get("reminders", []):
        slots = times_of(r)
        row = {**r, "slots": slots, "next": next((s for s in slots if minutes(s) > minutes(now)), None)}
        if r["kind"] == "supplement":
            row["taken"] = [s for s in r["times"] if (r["id"], s) in taken]
        else:
            row["target_ml"], row["drank_ml"] = target, daily.get("water_ml", 0) or 0
            row["expected_ml"] = water_expected(r, target, now)
        rows.append(row)
    return rows


def from_text(text):
    """'영양제 비타민D 아침 9시랑 저녁 9시에 알려줘', '물 2시간마다 알려줘' → 알림 설정. 못 읽으면 None."""
    if not any(w in text for w in ("알림", "알려줘", "알려 줘", "챙겨줘")):
        return None
    hours = []
    for ampm, h, m in re.findall(r"(오전|오후|아침|점심|저녁|밤)?\s*(\d{1,2})\s*시\s*(?:(\d{1,2})\s*분|반)?", text):
        h = int(h)
        if ampm in ("오후", "저녁", "밤") and h < 12:
            h += 12
        if ampm == "점심" and h < 6:
            h += 12
        mm = int(m) if m else (30 if re.search(rf"{h % 12 or h}\s*시\s*반", text) else 0)
        if 0 <= h <= 23:
            hours.append(f"{h:02d}:{mm:02d}")
    if "물" in text and not any(w in text for w in SUPPLEMENT_WORDS):
        every = re.search(r"(\d{1,2})\s*시간\s*(?:마다|간격)", text)
        mins = re.search(r"(\d{2,3})\s*분\s*(?:마다|간격)", text)
        step = int(every[1]) * 60 if every else int(mins[1]) if mins else 120
        return {"kind": "water", "every_min": max(30, min(360, step)), "start": hours[0] if len(hours) >= 2 else "09:00", "end": hours[1] if len(hours) >= 2 else "21:00"}
    word = next((w for w in SUPPLEMENT_WORDS if w in text), None)
    if word:
        name = re.search(rf"({word}\s*[A-Za-z0-9]*)", text)[1].strip()
        if not hours:
            hours = {"아침": ["08:00"], "점심": ["12:30"], "저녁": ["19:00"]}.get(next((w for w in ("아침", "점심", "저녁") if w in text), ""), ["09:00"])
        return {"kind": "supplement", "name": name, "times": sorted(set(hours))[:6], "dose": ""}
    return None


def now_hhmm():
    from storage import KST

    return datetime.now(KST).strftime("%H:%M")
