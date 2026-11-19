"""운동 모드: 오늘 루틴을 단계(준비 → 동작별 세트 → 마무리)로 펼치고, 동작마다 하는 방법을 붙인다.
다른 선택지(회복 기준 다른 부위 · 짧게 10분 · 강도 한 단계 조정)도 함께 만든다. 판단은 모두 코드가 한다.
"""

from datetime import date, timedelta

import media
from domain.exercise_library import DISCLAIMER, PHOTO_CREDIT, describe
from domain.training import GOALS, LEVELS, MOVES, routine

ROTATION = ("하체", "상체", "코어", "등", "가슴", "어깨", "팔", "전신")


def josa(word, with_final="이에요", without="예요"):
    """받침에 맞는 조사: '플랭크'+이에요, '스텝 터치'+예요."""
    last = word.strip()[-1:] if word else ""
    if "가" <= last <= "힣":
        return word + (with_final if (ord(last) - 0xAC00) % 28 else without)
    return word + with_final


def coach_line(name, x, t):
    """트레이너가 동작 시작 전에 해 주는 한마디."""
    amount = f"{x['reps']}회씩 {x['sets']}세트" if x["mode"] == "reps" else f"{x['hold_sec']}초씩 {x['sets']}세트"
    tempo = f" 템포는 내려가며 {x['tempo'][0]}초, 멈춰 {x['tempo'][1]}초, 올라오며 {x['tempo'][2]}초예요." if x["mode"] == "reps" else ""
    first = (t.get("cues") or [""])[0]
    return f"이번 동작은 {josa(name)}. {amount} 할게요.{tempo} {first}".strip()


def build(state, available=None):
    return build_from(routine(state, available if available is not None else state.get("exercise_minutes", 10)))


def build_from(r):
    from domain.exercise_library import trainer

    if not r["steps"]:
        return {"루틴": r, "단계": [], "안내": r["summary"], "주의": DISCLAIMER}
    steps = []
    for w in r["warmup"]:
        t = trainer(w["name"])
        steps.append({"kind": "warmup", **describe(w["name"]), **t, "mode": "time", "seconds": w["seconds"], "sets": 1, "rest": 0, "intro": f"준비 운동으로 {w['name']} {w['seconds']}초 할게요. 몸을 천천히 데워요."})
    for x in r["exercises"]:
        t = trainer(x["name"])
        steps.append({
            "kind": "exercise", **describe(x["name"]), **t, "mode": x["mode"], "reps": x["reps"],
            "seconds": x["hold_sec"] if x["mode"] != "reps" else x["work_sec"], "tempo": x["tempo"],
            "sets": x["sets"], "rest": x["rest_sec"], "guide": x["guide"], "intro": coach_line(x["name"], x, t),
        })
    for c in r["cooldown"]:
        t = trainer(c["name"])
        steps.append({"kind": "cooldown", **describe(c["name"]), **t, "mode": "time", "seconds": c["seconds"], "sets": 1, "rest": 0, "intro": f"마무리로 {c['name']} {c['seconds']}초 할게요. 천천히 호흡하세요."})
    for s in steps:  # 사진은 같은 출처로 중계해 앱(WebView)에서도 바로 보이게 한다
        s["photos"] = [media.proxied(u) for u in s["photos"]]
        s["credit"] = PHOTO_CREDIT if s["photos"] else ""
        s.setdefault("cues", [])
    return {"루틴": r, "단계": steps, "총 시간(초)": r["planned_sec"], "주의": DISCLAIMER}


def recent_bodies(state, day, days=2):
    since = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    return {w["body"] for w in state.get("workouts", []) if w.get("day", "") >= since}


def options(state, day):
    """오늘 추천 + 다른 선택지 3개. 각 선택지는 설정 변경 명령(apply)으로 바로 바꿀 수 있다."""
    current = state.get("body") or GOALS[state.get("goal", "체력")]
    level = state.get("level", "초보")
    minutes = state.get("exercise_minutes", 10)
    recent = recent_bodies(state, day)
    out = []
    rest = next((b for b in ROTATION if b != current and b not in recent), None)
    if rest:
        out.append({"title": f"{rest} 루틴", "why": "최근 2일 안에 하지 않은 부위라 회복된 근육을 써요", "apply": {"body": rest}})
    if minutes > 10:
        out.append({"title": "10분 전신 루틴", "why": "시간이 없을 때 전신을 가볍게 움직여요", "apply": {"body": "전신", "exercise_minutes": 10}})
    i = LEVELS.index(level)
    if i + 1 < len(LEVELS):
        out.append({"title": f"{current} · {LEVELS[i + 1]} 강도", "why": "지금 루틴이 쉬웠다면 강도를 한 단계 올려요", "apply": {"level": LEVELS[i + 1]}})
    if i > 0:
        out.append({"title": f"{current} · {LEVELS[i - 1]} 강도", "why": "힘들었다면 한 단계 쉬운 동작으로 바꿔요", "apply": {"level": LEVELS[i - 1]}})
    for o in out:
        preview = routine({**state, **o["apply"]}, o["apply"].get("exercise_minutes", minutes))
        o["summary"] = preview["summary"]
    return {"current": {"body": current, "level": level, "minutes": minutes, "recent": sorted(recent)}, "options": out[:3], "bodies": list(MOVES), "levels": list(LEVELS)}


# ── 나만의 루틴 ─────────────────────────────────────
def catalog():
    """루틴 만들기 화면에서 고를 수 있는 동작(부위별)과 기본 방식."""
    from domain.exercise_library import LIBRARY, trainer

    out = {}
    for body, moves in MOVES.items():
        out[body] = [{"name": n, "mode": "hold" if trainer(n).get("mode") in ("hold", "time") else "reps", "muscles": LIBRARY[n][5]} for n, _ in moves]
    return out


def save_custom(state, params):
    from domain.exercise_library import LIBRARY, trainer
    from uuid import uuid4

    name = str(params.get("name", "")).strip()
    items = params.get("items") or []
    if not 1 <= len(name) <= 30 or not 1 <= len(items) <= 10:
        raise ValueError("루틴 이름(30자 이내)과 동작 1~10개를 정하세요.")
    clean = []
    for x in items:
        ex = str(x.get("name", ""))
        if ex not in LIBRARY or ex == "마무리 호흡":
            raise ValueError("목록에 있는 동작을 고르세요.")
        mode = "hold" if trainer(ex).get("mode") in ("hold", "time") else "reps"
        sets, rest = int(x.get("sets", 3)), int(x.get("rest", 45))
        amount = int(x.get("amount", 12 if mode == "reps" else 30))
        ok = 1 <= sets <= 10 and 15 <= rest <= 180 and ((3 <= amount <= 50) if mode == "reps" else (10 <= amount <= 180))
        if not ok:
            raise ValueError("세트 1~10, 횟수 3~50(버티기 10~180초), 휴식 15~180초로 정하세요.")
        clean.append({"name": ex, "mode": mode, "sets": sets, "amount": amount, "rest": rest})
    routines = state.setdefault("my_routines", [])
    if len(routines) >= 10:
        raise ValueError("나만의 루틴은 10개까지 저장할 수 있어요.")
    routines.append({"id": uuid4().hex[:8], "name": name, "items": clean})
    return routines[-1]


def build_custom(state, rid):
    from domain.exercise_library import trainer
    from domain.training import COOLDOWN, WARMUP, MOVES as _M

    r = next((x for x in state.get("my_routines", []) if x["id"] == rid), None)
    if not r:
        raise ValueError("루틴을 찾지 못했어요.")
    guides = {n: g for moves in _M.values() for n, g in moves}
    exercises = []
    for x in r["items"]:
        t = trainer(x["name"])
        tempo = t.get("tempo", [2, 1, 2])
        item = {"name": x["name"], "guide": guides.get(x["name"], ""), "mode": x["mode"], "reps": x["amount"] if x["mode"] == "reps" else None,
                "hold_sec": x["amount"] if x["mode"] == "hold" else None, "tempo": tempo, "sets": x["sets"], "rest_sec": x["rest"]}
        item["work_sec"] = sum(tempo) * x["amount"] if x["mode"] == "reps" else x["amount"]
        exercises.append(item)
    total = sum(t for _, t in WARMUP) + sum(e["sets"] * (e["work_sec"] + e["rest_sec"]) for e in exercises) + sum(t for _, t in COOLDOWN)
    fake = {"body": r["name"], "level": "내 루틴", "minutes": round(total / 60), "planned_sec": total, "exercises": exercises,
            "warmup": [{"name": n, "seconds": t} for n, t in WARMUP], "cooldown": [{"name": n, "seconds": t} for n, t in COOLDOWN],
            "steps": [e["name"] for e in exercises], "move": " · ".join(e["name"] for e in exercises), "summary": f"{r['name']} · 약 {round(total / 60)}분", "reason": "나만의 루틴"}
    return build_from(fake)
