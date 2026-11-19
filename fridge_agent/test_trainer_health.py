"""트레이너식 운동 루틴, 구체적인 레시피(계량·손질·익힘 기준), 건강 체크, 나만의 루틴."""

import pytest
from fastapi.testclient import TestClient

import app as api
import health_check
import recipe_detail
from domain.training import routine


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    for key in ("FRIDGE_MODE", "FRIDGE_DEMO", "GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_trainer_routine_uses_reps_sets_tempo_and_fits_time():
    for level, sets, reps in (("초보", 2, 10), ("중급", 3, 12), ("숙련", 4, 15)):
        r = routine({"body": "하체", "level": level, "goal": "체력", "exercise_minutes": 30}, 30)
        main = [x for x in r["exercises"] if x["mode"] == "reps"]
        assert main and all(x["reps"] == reps for x in main) and r["planned_sec"] <= 30 * 60
        assert all(len(x["tempo"]) == 3 for x in main)
        assert any(x["mode"] == "hold" or x["name"] == "데드버그" for x in r["exercises"])  # 하체 날에도 코어 보조 동작
    short = routine({"body": "하체", "level": "중급", "goal": "체력", "exercise_minutes": 10}, 10)
    assert short["planned_sec"] <= 10 * 60


def test_workout_guide_has_trainer_cues_and_mistakes():
    api.run("하체 운동 20분 중급")
    g = TestClient(api.app).post("/api/workout/guide", json={}).json()
    kinds = [s["kind"] for s in g["단계"]]
    assert kinds[0] == "warmup" and kinds[-1] == "cooldown" and "exercise" in kinds
    squat = next(s for s in g["단계"] if s["name"] == "맨몸 스쿼트")
    assert squat["mode"] == "reps" and squat["reps"] == 12 and squat["cues"] and squat["mistakes"] and squat["easier"]
    assert "템포" in squat["intro"]
    assert all(s["mode"] == "time" for s in g["단계"] if s["kind"] != "exercise")


def test_recipe_detail_units_and_checks():
    assert recipe_detail.household("간장", 18) == "약 1큰술"
    assert recipe_detail.household("두부", 150) == "½모"
    assert recipe_detail.household("달걀", 100) == "2개"
    api.run("추가 돼지고기")
    g = TestClient(api.app).post("/api/guide", json={"title": "제육볶음", "servings": 2}).json()
    prep, fry = g["단계"][0], next(c for c in g["단계"] if c["동작"] == "볶기")
    assert prep["종류"] == "prep" and any("양파" in t for t in prep["손질"])
    assert "분홍빛" in fry["익힘 기준"]
    assert g["단계"][-1]["종류"] == "finish" and "냉장" in g["단계"][-1]["익힘 기준"]


def test_health_check_ranges_and_apply():
    m = health_check.Metrics(sex="남", height_cm=175, weight_kg=82, waist_cm=92, sbp=150, dbp=95, glucose=130, ldl=195, hdl=38, tg=180)
    r = health_check.evaluate(m)
    levels = {x["항목"]: x["판정"] for x in r["결과"]}
    assert levels["체질량지수(BMI)"] == "1단계 비만" and levels["허리둘레"] == "복부비만" and levels["혈압"] == "고혈압 범위"
    assert len(r["진료 권유"]) == 3  # 혈압·혈당·LDL 190 이상
    assert set(r["반영할 설정"]) >= {"weight", "sodium", "sugar", "fat"}
    with pytest.raises(ValueError):
        api.run("건강반영")
    api.run("데모")
    api.run("건강체크", params={"sex": "남", "height_cm": 175, "weight_kg": 82, "sbp": 135, "dbp": 85})
    api.run("건강반영")
    p = api.run("저녁 추천해줘")["계획"]
    import re

    sodium = [float(re.search(r"나트륨 ([\d.]+)", " ".join(x["근거"]))[1]) for x in p["추천 후보"]]
    assert sodium == sorted(sodium)  # 혈압 주의가 반영되면 나트륨 낮은 순(같은 부족 재료 수 안에서)
    assert all(any("kcal" in g for g in x["근거"]) for x in p["추천 후보"])  # 체중 관리도 반영
    latest = TestClient(api.app).get("/api/health/latest").json()
    assert latest["있음"] and latest["반영됨"]
    with pytest.raises(ValueError):
        api.run("건강체크", params={"sbp": 500})


def test_custom_routine_save_run_delete():
    with pytest.raises(ValueError):
        api.run("내루틴저장", params={"name": "x", "items": [{"name": "없는 동작"}]})
    api.run("내루틴저장", params={"name": "출근 전", "items": [{"name": "맨몸 스쿼트", "sets": 2, "amount": 15, "rest": 30}, {"name": "플랭크", "sets": 2, "amount": 40, "rest": 30}]})
    c = TestClient(api.app)
    rid = c.post("/api/workout/guide", json={}).json()["내 루틴"][0]["id"]
    g = c.post("/api/workout/guide", json={"routine_id": rid}).json()
    main = [s for s in g["단계"] if s["kind"] == "exercise"]
    assert [(s["name"], s.get("reps"), s["seconds"], s["sets"]) for s in main] == [("맨몸 스쿼트", 15, 75, 2), ("플랭크", None, 40, 2)]
    api.run("내루틴삭제 " + rid)
    assert c.post("/api/workout/guide", json={"routine_id": rid}).status_code == 404


def test_coach_routes_health_and_weekly():
    api.run("데모")
    assert "건강 체크" in api.run("건강검진에서 혈압이 높대")["계획"]["안내"]
    assert len(api.run("일주일 다이어트 식단 짜줘")["계획"]["주간"]) == 7
