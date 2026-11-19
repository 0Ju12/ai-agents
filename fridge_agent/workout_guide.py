"""운동 모드: 오늘 루틴을 단계(준비 → 동작별 세트 → 마무리)로 펼치고, 동작마다 하는 방법을 붙인다.
다른 선택지(회복 기준 다른 부위 · 짧게 10분 · 강도 한 단계 조정)도 함께 만든다. 판단은 모두 코드가 한다.
"""

from datetime import date, timedelta

import media
from domain.exercise_library import DISCLAIMER, PHOTO_CREDIT, describe
from domain.training import GOALS, LEVELS, MOVES, routine

ROTATION = ("하체", "상체", "코어", "등", "가슴", "어깨", "팔", "전신")


def build(state, available=None):
    r = routine(state, available if available is not None else state.get("exercise_minutes", 10))
    if not r["steps"]:
        return {"루틴": r, "단계": [], "안내": r["summary"], "주의": DISCLAIMER}
    steps = [{"kind": "warmup", **describe("제자리 걷기"), "seconds": 60, "sets": 1, "rest": 0}]
    for x in r["exercises"]:
        steps.append({"kind": "exercise", **describe(x["name"]), "seconds": x["work_sec"], "sets": x["sets"], "rest": x["rest_sec"], "guide": x["guide"]})
    steps.append({"kind": "cooldown", **describe("마무리 호흡"), "seconds": 60, "sets": 1, "rest": 0})
    for s in steps:  # 사진은 같은 출처로 중계해 앱(WebView)에서도 바로 보이게 한다
        s["photos"] = [media.proxied(u) for u in s["photos"]]
        s["credit"] = PHOTO_CREDIT if s["photos"] else ""
    total = sum(s["sets"] * (s["seconds"] + s["rest"]) for s in steps)
    return {"루틴": r, "단계": steps, "총 시간(초)": total, "주의": DISCLAIMER}


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
