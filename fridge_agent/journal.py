from datetime import date, timedelta
from domain.catalog import FIELDS
from domain.kitchen import select_meal
from domain.training import routine


def health_totals(daily):
    """하루 합계. 영양을 모르는 기록이 있어도 아는 값은 더하고, 몇 건이 빠졌는지 함께 알린다."""
    entries = daily.get("intake", [])
    manual, partial = {}, {}
    for k in FIELDS:
        vals = [x.get("nutrients", {}).get(k) for x in entries]
        known = [v for v in vals if v is not None]
        manual[k] = round(sum(known), 1) if known else None
        partial[k] = len(vals) - len(known)
    manual.update({k: daily.get(k) for k in ("water_ml", "sleep_hours", "exercise_minutes")})
    device = daily.get("health_connect", {})
    return {
        k: {
            "value": device.get(k, v),
            "source": "Health Connect" if k in device else (("직접 기록" + (f" · {partial[k]}건 미확인" if partial.get(k) else "")) if v is not None else (f"{partial[k]}건 영양 미확인" if partial.get(k) else None)),
        }
        for k, v in manual.items()
    }


def summary(state, day):
    entries = state["daily"].get(day, {})
    totals = health_totals(entries)
    goals = state.get("targets", {})
    hints = []
    for k, label, source in (
        ("protein_g", "단백질", "두부나 달걀을 넣은 식사를 살펴보세요."),
        ("water_ml", "수분", "다음에 물을 마시면 양을 기록해 보세요."),
        ("fiber_g", "식이섬유", "채소나 익힌 콩을 곁들이는 메뉴를 살펴보세요."),
    ):
        actual = totals[k]["value"]
        target = goals.get(k)
        if actual is not None and target and actual < target:
            hints.append({"label": label, "remaining": round(target - actual, 1), "advice": source})
    first = date.fromisoformat(day) - timedelta(days=6)
    week = [
        {"day": d.isoformat(), "totals": health_totals(state["daily"].get(d.isoformat(), {}))}
        for d in (first + timedelta(days=i) for i in range(7))
    ]
    records = state["records"]
    n = len(records)
    return {
        "totals": totals,
        "targets": goals,
        "hints": hints,
        "week": week,
        "metrics": {
            "cooks": n,
            "planned_vs_actual_mae_min": round(sum(abs(x["actual"] - x["planned"]) for x in records) / n, 1)
            if n
            else None,
            "recorded_days": len(
                [d for d in week if any(v["value"] is not None for v in d["totals"].values())]
            ),
        },
    }


def weekly(state, meals, refs, day):
    options = []
    for title in meals:
        meal = select_meal({**state, "wanted": title}, meals, refs, day)
        if meal.get("메뉴"):
            options.append(
                (
                    len(meal["부족분"]),
                    -float(meal["영양"].get("protein_g") or 0) if state.get("diet") == "단백질 우선" else 0,
                    title,
                )
            )
    options.sort()
    first = date.fromisoformat(day)
    result = []
    for i in range(7):
        title = options[i % len(options)][2] if options else None
        current = (first + timedelta(days=i)).isoformat()
        plan = select_meal({**state, "wanted": title}, meals, refs, current) if title else {}
        result.append(
            {
                "day": current,
                "meal": title,
                "missing": plan.get("부족량(g)", {}),
                "workout": routine(state, max(0, state["minutes"] - plan.get("조리시간(분)", 0)))["summary"]
                if i % 2 == 0
                else "휴식 또는 가벼운 산책",
            }
        )
    return result
