"""Small original exercise library. Minutes include rests and transitions."""

LEVELS = ("초보", "중급", "숙련")
GOALS = {"체력": "전신", "근력": "하체", "체중 관리": "전신"}
MOVES = {
    "전신": [
        ("제자리 걷기", "편안하게 팔을 흔들며 걷기"),
        ("스텝 터치", "좌우로 한 걸음씩 이동"),
        ("빠른 제자리 걷기", "대화할 수 있는 속도로 걸음 올리기"),
    ],
    "하체": [
        ("의자 앉았다 일어나기", "안정된 의자 앞에서 발을 바닥에 고정"),
        ("맨몸 스쿼트", "편한 범위까지 천천히 앉기"),
        ("리버스 런지", "한 발씩 뒤로 내디디기"),
    ],
    "상체": [
        ("벽 밀기", "벽에 손을 대고 천천히 팔 굽히기"),
        ("인클라인 푸시업", "고정된 높은 지지대를 사용"),
        ("푸시업", "몸통을 곧게 유지하며 수행"),
    ],
    "코어": [
        ("버드독", "네발 자세에서 반대쪽 팔과 다리를 뻗기"),
        ("데드버그", "누워서 반대쪽 팔다리 내리기"),
        ("플랭크", "허리가 처지기 전에 쉬기"),
    ],
    "등": [
        ("엎드린 W", "팔꿈치를 굽히고 견갑골 모으기"),
        ("리버스 스노우엔젤", "어깨가 편한 범위에서 팔 움직이기"),
        ("프론 Y 레이즈", "팔을 Y자로 들었다 내려놓기"),
    ],
    "어깨": [
        ("벽 슬라이드", "등을 벽에 대고 팔을 미끄러뜨리기"),
        ("팔 벌려 버티기", "어깨 높이에서 짧게 유지"),
        ("숄더 탭", "안정된 지지 자세에서 어깨 터치"),
    ],
    "가슴": [
        ("벽 푸시업", "손을 가슴높이에 두기"),
        ("인클라인 푸시업", "단단히 고정된 지지대 사용"),
        ("푸시업", "목에 힘을 빼고 수행"),
    ],
    "팔": [
        ("자가저항 컬", "반대손으로 가볍게 저항 주기"),
        ("좁은 벽 푸시업", "팔꿈치를 몸 가까이 유지"),
        ("좁은 인클라인 푸시업", "지지대에서 몸을 밀어내기"),
    ],
}
EQUIPMENT = {
    "하체": ("고블릿 스쿼트", "덤벨을 가슴 가까이 고정"),
    "등": ("덤벨 로우", "한 손을 안정적으로 지지"),
    "팔": ("덤벨 컬", "반동 없이 천천히 굽히기"),
    "어깨": ("가벼운 덤벨 레이즈", "통증 없는 범위에서 들기"),
}


CORE_ADD = {0: "데드버그", 1: "플랭크", 2: "플랭크"}  # 상체·하체 날에 덧붙이는 코어 동작
WARMUP = [("제자리 걷기", 60), ("팔 돌리기", 45)]
COOLDOWN = [("허벅지 앞 스트레칭", 30), ("가슴 스트레칭", 20), ("마무리 호흡", 40)]


def set_seconds(name, item):
    """한 세트에 걸리는 시간(초): 횟수형은 템포 × 횟수, 버티기형은 버티는 시간."""
    if item["mode"] in ("hold", "time"):
        return item["hold_sec"]
    return sum(item["tempo"]) * item["reps"]


def routine(state, available):
    """트레이너처럼 짠 오늘 루틴: 준비 운동 → 본운동(횟수·세트·휴식·템포) → 마무리 스트레칭.
    가용 시간에 맞춰 동작 수와 세트 수를 조절하고, 최근 '어려움' 피드백이면 한 단계 쉽게 한다."""
    from domain.exercise_library import LEVEL_PLAN, trainer

    body = state.get("body") or GOALS[state.get("goal", "체력")]
    level = state.get("level", "초보")
    difficulty = LEVELS.index(level)
    last = next((x for x in reversed(state.get("workouts", [])) if x["body"] == body), {})
    easier = last.get("effort") == "어려움"
    if easier:
        difficulty = max(0, difficulty - 1)
    minutes = min(max(available, 0), state.get("exercise_minutes", 10))
    if minutes < 5:
        return {"body": body, "minutes": 0, "steps": [], "exercises": [], "summary": "운동 시간 부족 · 5분 이상 확보하세요."}
    plan = LEVEL_PLAN[LEVELS[difficulty]]
    picks = {0: [0, 1], 1: [0, 1, 2], 2: [2, 1, 2]}[difficulty]
    chosen = []
    for i in picks:
        item = MOVES[body][i]
        if i == 2 and difficulty and "덤벨" in state.get("gear", []) and body in EQUIPMENT and EQUIPMENT[body] not in chosen:
            item = EQUIPMENT[body]
        if item not in chosen:
            chosen.append(item)
    if body not in ("코어", "전신"):
        core = CORE_ADD[difficulty]
        guide = next(g for n, g in MOVES["코어"] if n == core)
        chosen.append((core, guide))
    names = {n for n, _ in chosen}
    warmup = [(n, t) for n, t in WARMUP if n not in names] or [("팔 돌리기", 45)]  # 본운동과 겹치는 준비 운동은 뺀다
    budget = minutes * 60 - sum(t for _, t in warmup) - sum(t for _, t in COOLDOWN)

    def program(sets):
        out = []
        for name, guide in chosen:
            t = trainer(name)
            mode = t.get("mode") if t.get("mode") in ("hold", "time") else "reps"  # time: 정해진 시간 동안 계속(걷기 등)
            reps = max(6, plan["reps"] - (2 if easier else 0))
            hold = max(15, plan["hold"] - (5 if easier else 0)) + (20 if mode == "time" else 0)
            item = {"name": name, "guide": guide, "mode": mode, "reps": reps if mode == "reps" else None,
                    "hold_sec": hold if mode != "reps" else None, "tempo": t.get("tempo", [2, 1, 2]),
                    "sets": sets, "rest_sec": plan["rest"] + (15 if easier else 0)}
            item["work_sec"] = set_seconds(name, item)
            out.append(item)
        return out

    sets = plan["sets"]
    exercises = program(sets)
    used = lambda ex: sum(x["sets"] * (x["work_sec"] + x["rest_sec"]) for x in ex)
    while used(exercises) > budget and sets > 1:  # 시간이 모자라면 세트를 줄이고
        sets -= 1
        exercises = program(sets)
    while used(exercises) > budget and len(exercises) > 1:  # 그래도 모자라면 보조 동작부터 뺀다
        exercises.pop()
    while used(exercises) + (exercises[0]["work_sec"] + exercises[0]["rest_sec"]) * len(exercises) <= budget and sets < plan["sets"] + 2:
        sets += 1  # 시간이 남으면 세트를 늘린다(처방 +2세트까지)
        exercises = program(sets)[: len(exercises)]
    def describe_set(x):
        amount = f"{x['reps']}회" if x["mode"] == "reps" else f"{x['hold_sec']}초 버티기" if x["mode"] == "hold" else f"{x['hold_sec']}초 동안"
        return f"{x['name']} {amount} × {x['sets']}세트 · 휴식 {x['rest_sec']}초 · {x['guide']}"
    steps = ["준비 운동: " + " · ".join(f"{n} {t}초" for n, t in warmup)]
    steps += [describe_set(x) for x in exercises]
    steps.append("마무리 스트레칭: " + " · ".join(f"{n} {t}초" for n, t in COOLDOWN))
    move = " · ".join(x["name"] for x in exercises)
    total = sum(t for _, t in warmup) + used(exercises) + sum(t for _, t in COOLDOWN)
    return {
        "body": body,
        "level": level,
        "minutes": minutes,
        "planned_sec": total,
        "steps": steps,
        "move": move,
        "exercises": exercises,
        "warmup": [{"name": n, "seconds": t} for n, t in warmup],
        "cooldown": [{"name": n, "seconds": t} for n, t in COOLDOWN],
        "reason": "최근 어려움 피드백으로 강도 조정"
        if easier
        else f"{level} · {state.get('goal', '체력')} · 보유 기구 기준",
        "summary": f"{body} · {move} · 약 {round(total / 60)}분",
    }
