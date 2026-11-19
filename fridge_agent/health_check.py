"""건강 체크: 인바디·건강검진 수치를 국내 공개 기준과 비교하고 생활 습관을 안내한다 (웰니스 참고용).

기준값 출처(성인 기준, 화면에 함께 표시)
- 체질량지수(BMI)·허리둘레: 대한비만학회 비만 진료지침 2022
- 혈압: 대한고혈압학회 고혈압 진료지침 2022
- 공복혈당: 대한당뇨병학회 당뇨병 진료지침
- 총콜레스테롤·LDL·HDL·중성지방: 한국지질·동맥경화학회 이상지질혈증 진료지침
- 체지방률: 일반적으로 쓰는 참고값(남 25%, 여 30%)이며 공식 진단 기준은 아니다

이 결과는 진단이 아니다. 질환이 의심되는 범위면 진료를 권한다.
"""

from datetime import datetime

from pydantic import BaseModel, Field

DISCLAIMER = "건강검진 결과 해석과 치료는 의료진의 판단을 따르세요. 한끼의 안내는 생활 습관 참고 정보예요."
SOURCES = [
    "대한비만학회 비만 진료지침 2022 (BMI·허리둘레)",
    "대한고혈압학회 고혈압 진료지침 2022 (혈압)",
    "대한당뇨병학회 진료지침 (공복혈당)",
    "한국지질·동맥경화학회 이상지질혈증 진료지침 (콜레스테롤·중성지방)",
]


class Metrics(BaseModel):
    sex: str = Field(default="", pattern="^(남|여|)$")
    height_cm: float | None = Field(default=None, ge=100, le=230)
    weight_kg: float | None = Field(default=None, ge=25, le=300)
    body_fat_pct: float | None = Field(default=None, ge=3, le=70)
    muscle_kg: float | None = Field(default=None, ge=5, le=80)
    waist_cm: float | None = Field(default=None, ge=40, le=200)
    sbp: int | None = Field(default=None, ge=60, le=260)
    dbp: int | None = Field(default=None, ge=30, le=160)
    glucose: int | None = Field(default=None, ge=40, le=500)
    total_chol: int | None = Field(default=None, ge=60, le=500)
    ldl: int | None = Field(default=None, ge=20, le=400)
    hdl: int | None = Field(default=None, ge=10, le=150)
    tg: int | None = Field(default=None, ge=20, le=3000)


def row(name, value, unit, level, label, ref):
    return {"항목": name, "값": value, "단위": unit, "판정": label, "수준": level, "참고 범위": ref}


def evaluate(m: Metrics):
    rows, focus, see_doctor = [], set(), []
    if m.height_cm and m.weight_kg:
        bmi = round(m.weight_kg / (m.height_cm / 100) ** 2, 1)
        if bmi < 18.5:
            r = ("주의", "저체중")
        elif bmi < 23:
            r = ("정상", "정상")
        elif bmi < 25:
            r = ("주의", "비만 전단계")
            focus.add("weight")
        elif bmi < 30:
            r = ("높음", "1단계 비만")
            focus.add("weight")
        else:
            r = ("높음", "2단계 이상 비만")
            focus.add("weight")
        rows.append(row("체질량지수(BMI)", bmi, "kg/㎡", *r, "18.5~22.9 정상 · 23~24.9 비만 전단계 · 25 이상 비만"))
    if m.waist_cm and m.sex:
        cut = 90 if m.sex == "남" else 85
        high = m.waist_cm >= cut
        if high:
            focus.add("weight")
        rows.append(row("허리둘레", m.waist_cm, "cm", "높음" if high else "정상", "복부비만" if high else "정상", f"{m.sex}성 {cut}cm 이상 복부비만"))
    if m.body_fat_pct and m.sex:
        cut = 25 if m.sex == "남" else 30
        high = m.body_fat_pct >= cut
        rows.append(row("체지방률", m.body_fat_pct, "%", "주의" if high else "정상", "높은 편" if high else "정상 범위", f"{m.sex}성 {cut}% 이상이면 높은 편(일반 참고값)"))
        if high:
            focus.add("weight")
    if m.muscle_kg and m.weight_kg:
        rows.append(row("골격근량", m.muscle_kg, "kg", "정보", f"체중의 {round(m.muscle_kg / m.weight_kg * 100)}%", "변화 추이를 보며 근력 운동을 꾸준히"))
    if m.sbp and m.dbp:
        if m.sbp >= 140 or m.dbp >= 90:
            r = ("높음", "고혈압 범위")
            see_doctor.append("혈압이 고혈압 범위예요. 다시 측정해 보고 진료를 받아 보세요.")
        elif m.sbp >= 130 or m.dbp >= 80:
            r = ("주의", "고혈압 전단계")
        elif m.sbp >= 120:
            r = ("주의", "주의 혈압")
        else:
            r = ("정상", "정상")
        if r[0] != "정상":
            focus.add("sodium")
        rows.append(row("혈압", f"{m.sbp}/{m.dbp}", "mmHg", *r, "120/80 미만 정상 · 130~139/80~89 전단계 · 140/90 이상 고혈압"))
    if m.glucose:
        if m.glucose >= 126:
            r = ("높음", "당뇨병 의심 범위")
            see_doctor.append("공복혈당이 126mg/dL 이상이에요. 재검사와 진료를 받아 보세요.")
        elif m.glucose >= 100:
            r = ("주의", "공복혈당장애 범위")
        else:
            r = ("정상", "정상")
        if r[0] != "정상":
            focus.add("sugar")
        rows.append(row("공복혈당", m.glucose, "mg/dL", *r, "100 미만 정상 · 100~125 공복혈당장애 · 126 이상 당뇨병 의심"))
    if m.total_chol:
        r = ("정상", "적정") if m.total_chol < 200 else ("주의", "경계") if m.total_chol < 240 else ("높음", "높음")
        if r[0] != "정상":
            focus.add("fat")
        rows.append(row("총콜레스테롤", m.total_chol, "mg/dL", *r, "200 미만 적정 · 200~239 경계 · 240 이상 높음"))
    if m.ldl:
        r = ("정상", "정상") if m.ldl < 130 else ("주의", "경계") if m.ldl < 160 else ("높음", "높음")
        if m.ldl >= 190:
            see_doctor.append("LDL 콜레스테롤이 매우 높아요(190 이상). 진료를 받아 보세요.")
        if r[0] != "정상":
            focus.add("fat")
        rows.append(row("LDL 콜레스테롤", m.ldl, "mg/dL", *r, "130 미만 · 130~159 경계 · 160 이상 높음 (위험 요인에 따라 목표가 달라요)"))
    if m.hdl:
        low = m.hdl < 40
        if low:
            focus.add("cardio")
        rows.append(row("HDL 콜레스테롤", m.hdl, "mg/dL", "주의" if low else "정상", "낮음" if low else "정상", "40 미만이면 낮음 · 60 이상이면 좋음"))
    if m.tg:
        r = ("정상", "적정") if m.tg < 150 else ("주의", "경계") if m.tg < 200 else ("높음", "높음")
        if m.tg >= 500:
            see_doctor.append("중성지방이 매우 높아요(500 이상). 진료를 받아 보세요.")
        if r[0] != "정상":
            focus.update({"sugar", "fat"})
        rows.append(row("중성지방", m.tg, "mg/dL", *r, "150 미만 적정 · 150~199 경계 · 200 이상 높음"))
    tips = {
        "weight": "주 150분 이상 빠르게 걷기 같은 유산소 운동과 주 2회 근력 운동을 해요. 한 끼 열량이 낮은 메뉴를 우선 추천할게요.",
        "sodium": "국·찌개 국물을 적게 먹고 짠 반찬을 줄여요. 나트륨이 적은 메뉴를 우선 추천할게요.",
        "sugar": "단 음료와 흰 빵·과자처럼 정제 탄수화물을 줄이고 식후 10~15분 걸어요. 탄수화물이 적은 메뉴를 우선 추천할게요.",
        "fat": "버터·튀김·기름진 고기를 줄이고 채소·콩·생선을 늘려요. 지방이 적은 메뉴를 우선 추천할게요.",
        "cardio": "꾸준한 유산소 운동이 HDL 을 높이는 데 도움이 돼요.",
    }
    return {
        "결과": rows,
        "생활 안내": [tips[k] for k in ("weight", "sodium", "sugar", "fat", "cardio") if k in focus],
        "진료 권유": see_doctor,
        "반영할 설정": sorted(focus),
        "기준 출처": SOURCES,
        "안내": DISCLAIMER,
    }


def save(state, m: Metrics, day):
    result = evaluate(m)
    checks = state.setdefault("health_checks", [])
    checks.append({"day": day, "at": datetime.now().isoformat(timespec="minutes"), "values": m.model_dump(exclude_none=True), "focus": result["반영할 설정"]})
    del checks[:-12]
    return result


def apply(state):
    """마지막 체크 결과를 식단·운동 설정에 반영한다 (사용자가 버튼을 눌렀을 때만)."""
    checks = state.get("health_checks", [])
    if not checks:
        raise ValueError("먼저 건강 체크를 입력하세요.")
    focus = set(checks[-1]["focus"])
    state["health_focus"] = sorted(focus & {"weight", "sodium", "sugar", "fat"})
    if "weight" in focus:
        state["goal"] = "체중 관리"
    return state["health_focus"]
