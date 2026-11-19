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


def routine(state, available):
    body = state.get("body") or GOALS[state.get("goal", "체력")]
    level = state.get("level", "초보")
    difficulty = LEVELS.index(level)
    last = next((x for x in reversed(state.get("workouts", [])) if x["body"] == body), {})
    easier = last.get("effort") == "어려움"
    if easier:
        difficulty = max(0, difficulty - 1)
    minutes = min(max(available, 0), state.get("exercise_minutes", 10))
    if minutes < 5:
        return {"body": body, "minutes": 0, "steps": [], "summary": "운동 시간 부족 · 5분 이상 확보하세요."}
    move, guide = MOVES[body][difficulty]
    if difficulty and "덤벨" in state.get("gear", []) and body in EQUIPMENT:
        move, guide = EQUIPMENT[body]
    work = (20, 30, 40)[difficulty]
    if easier:
        work = max(15, work - 5)
    steps = [
        "제자리 걷기와 가벼운 관절 움직임 1분",
        f"{move} {work}초 + 휴식 {60 - work}초를 {minutes - 2}회 · {guide}",
        "천천히 호흡하며 마무리 1분",
    ]
    return {
        "body": body,
        "level": level,
        "minutes": minutes,
        "steps": steps,
        "move": move,
        "reason": "최근 어려움 피드백으로 강도 조정"
        if easier
        else f"{level} · {state.get('goal', '체력')} · 보유 기구 기준",
        "summary": f"{body} · {move} · 휴식 포함 {minutes}분",
    }
