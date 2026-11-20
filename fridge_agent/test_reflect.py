"""모든 명령·API 가 실제로 상태에 반영되는지 확인한다 (실행 → 상태 재조회 → 값 비교)."""

import pytest
from fastapi.testclient import TestClient

import app as api
import gateway
from fake_llm import FakeChat


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    for key in ("FRIDGE_MODE", "FRIDGE_DEMO", "GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY", "FOODSAFETY_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def c():
    return TestClient(api.app)


def state(c):
    return c.get("/api/state").json()


def say(c, message, **params):
    r = c.post("/api/chat", json={"message": message, "params": params})
    assert r.status_code == 200, (message, r.json())
    return r.json()


def test_pantry_commands_reflect(c):
    say(c, "입고", name="두부", quantity=300, unit="g", expires="2030-01-01")
    say(c, "추가 양파, 대파")
    s = state(c)
    assert {"두부", "양파", "대파"} <= set(s["냉장고"])
    tofu = next(l for l in s["포장"] if l["item"] == "두부")
    assert tofu["grams"] == 300 and tofu["expires"] == "2030-01-01"
    say(c, "포장삭제 " + tofu["id"])
    say(c, "삭제 대파")
    assert set(state(c)["냉장고"]) == {"양파"}
    say(c, "데모")
    import autopilot

    assert len(state(c)["포장"]) == len(autopilot.DEMO_LOTS)


def test_menu_swap_cook_eat_reflect(c):
    say(c, "입고", name="달걀", quantity=500, unit="g")
    say(c, "입고", name="양파", quantity=200, unit="g")
    say(c, "입고", name="식용유", quantity=100, unit="g")
    assert say(c, "메뉴 대파 달걀볶음")["계획"]["메뉴"] == "대파 달걀볶음"
    assert say(c, "대체 양파")["계획"]["메뉴"] == "양파 달걀볶음"
    before = next(l for l in state(c)["포장"] if l["item"] == "달걀")["grams"]
    r = say(c, "조리 2인분 12분")
    after = next(l for l in r["포장"] if l["item"] == "달걀")["grams"]
    assert before - after == 200 and r["남은 음식"] == {"양파 달걀볶음": 2}
    r = say(c, "섭취 양파 달걀볶음")
    assert r["남은 음식"] == {"양파 달걀볶음": 1}
    intake = r["오늘 기록"]["intake"]
    assert intake[-1]["title"] == "양파 달걀볶음" and intake[-1]["nutrients"]["kcal"] > 0
    assert r["건강"]["totals"]["kcal"]["value"] == intake[-1]["nutrients"]["kcal"]


def test_cart_flow_reflect(c):
    say(c, "입고", name="두부", quantity=100, unit="g")
    say(c, "메뉴 두부 달걀찜")
    say(c, "장바구니담기", servings=2)
    cart = state(c)["장바구니"]
    assert set(cart) == {"두부", "달걀"} and cart["두부"]["grams"] == 100
    say(c, "구매완료 달걀", quantity=500, unit="g")
    s = state(c)
    assert "달걀" not in s["장바구니"] and "달걀" in s["냉장고"]
    say(c, "장바구니삭제 두부")
    assert state(c)["장바구니"] == {}


def test_daily_records_reflect(c):
    say(c, "물 300")
    say(c, "물 한 잔")
    say(c, "수면 7시간 30분")
    s = state(c)
    assert s["오늘 기록"]["water_ml"] == 550 and s["오늘 기록"]["sleep_hours"] == 7.5
    assert s["건강"]["totals"]["water_ml"]["value"] == 550


def test_meal_photo_reflects_dishes_ingredients_and_unknowns(c):
    """사진 식사: 레시피 요리·재료·추정 주재료·미확인이 섞여도 하루 합계가 비지 않는다."""
    r = say(c, "사진식사", items=[
        {"name": "김치찌개", "grams": 400},
        {"name": "밥", "grams": 210},
        {"name": "된장국", "grams": 300, "parts": [{"name": "된장", "grams": 15}]},
        {"name": "떡볶이", "grams": 300, "parts": [{"name": "떡", "grams": 200}]},
    ])
    intake = r["오늘 기록"]["intake"]
    assert [x["title"] for x in intake] == ["김치찌개", "밥", "된장국", "떡볶이"]
    assert "돼지고기 김치찌개" in intake[0]["source"] and "USDA" in intake[1]["source"]
    assert intake[3]["unverified"] is True and intake[3]["nutrients"] == {}
    kcal = r["건강"]["totals"]["kcal"]
    assert kcal["value"] == round(sum(x["nutrients"]["kcal"] for x in intake[:3]), 1)
    assert "1건 미확인" in kcal["source"]
    assert "식사 4가지를 기록" in r["계획"]["안내"] and "떡볶이" in r["계획"]["안내"]
    r = say(c, "섭취삭제 3")
    assert len(r["오늘 기록"]["intake"]) == 3 and "미확인" not in (r["건강"]["totals"]["kcal"]["source"] or "")
    with pytest.raises(AssertionError):
        say(c, "섭취삭제 9")


def test_meal_photo_endpoint_gives_basis_and_kcal(c, monkeypatch):
    import base64

    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    monkeypatch.setenv("GMS_PROVIDER", "openai")
    monkeypatch.setattr(gateway, "ChatOpenAI", FakeChat.factory(plan={"Sight": {"items": [{"name": "제육볶음", "grams": 250, "confidence": 0.8}, {"name": "밥", "grams": 210, "confidence": 0.9}]}}))
    image = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 400).decode()
    r = c.post("/api/photo", json={"kind": "meal", "image": image}).json()
    assert r["후보"][0]["근거"].startswith("한끼 레시피 ‘제육볶음’") and r["후보"][0]["예상 kcal"] > 0
    assert r["예상 영양"]["합계"]["kcal"] > 0


def test_settings_and_condition_commands_reflect(c):
    say(c, "설정", minutes=25, exercise_minutes=20, diet="단백질 우선", level="중급", body="하체", area="강남", budget_krw=8000, targets={"water_ml": 2000})
    s = state(c)["설정"]
    assert (s["minutes"], s["exercise_minutes"], s["diet"], s["level"], s["body"], s["area"]) == (25, 20, "단백질 우선", "중급", "하체", "강남")
    assert s["targets"]["water_ml"] == 2000
    say(c, "시간 40")
    say(c, "부위 코어")
    say(c, "목표 다이어트")
    s = state(c)
    assert s["총 가용 시간"] == 40 and s["설정"]["body"] == "코어" and s["설정"]["goal"] == "체중 관리"
    assert s["운동 계획"]["body"] == "코어"
    say(c, "시간대 2030-01-02 18:00")
    assert state(c)["설정"]["window"]["start"] == "18:00"
    say(c, "시간대 해제")
    assert state(c)["설정"].get("window") is None


def test_workout_done_adjusts_next_routine(c):
    say(c, "설정", body="하체", level="중급", exercise_minutes=20)
    say(c, "운동완료", minutes=20, effort="어려움", body="하체")
    s = state(c)
    assert s["운동 기록"][-1]["effort"] == "어려움" and s["오늘 기록"]["exercise_minutes"] == 20
    assert "강도 조정" in s["운동 계획"]["reason"]


def test_reminders_crud_reflect(c):
    say(c, "알림추가", kind="water", start="09:00", end="21:00", every_min=120, cup_ml=250)
    say(c, "비타민D 아침 9시에 알려줘")
    items = c.get("/api/reminders").json()["items"]
    assert [x["kind"] for x in items] == ["water", "supplement"]
    rid = items[1]["id"]
    say(c, "영양제복용 " + rid)
    assert c.get("/api/reminders").json()["items"][1]["taken"]
    say(c, "알림토글 " + rid)
    assert c.get("/api/reminders").json()["items"][1]["enabled"] is False
    say(c, "알림삭제 " + rid)
    assert len(c.get("/api/reminders").json()["items"]) == 1


def test_health_custom_routine_links_reflect(c):
    say(c, "건강체크", sex="여", height_cm=160, weight_kg=66, sbp=125, dbp=78)
    h = c.get("/api/health/latest").json()
    assert h["있음"] and h["결과"][0]["판정"] == "1단계 비만"
    say(c, "건강반영")
    assert set(c.get("/api/health/latest").json()["반영됨"]) >= {"weight", "sodium"}
    say(c, "건강반영해제")
    assert c.get("/api/health/latest").json()["반영됨"] == []
    say(c, "내루틴저장", name="점심 10분", items=[{"name": "푸시업", "sets": 2, "amount": 10, "rest": 30}])
    routines = c.post("/api/workout/guide", json={}).json()["내 루틴"]
    assert routines[0]["name"] == "점심 10분"
    say(c, "영상링크", menu="두부구이", url="https://youtu.be/abcdefghijk")
    m = c.post("/api/guide/media", json={"menu": "두부구이", "steps": []}).json()
    assert m["youtube"]["data"][0]["id"] == "abcdefghijk"


def test_plans_logs_export_erase(c):
    p = c.post("/api/plans", json={"title": "저녁", "trip_date": "2030-01-01", "start_time": "18:00", "end_time": "19:00", "items": []}).json()
    pid = p.get("id") or p.get("plan", {}).get("id")
    assert c.get("/api/plans").json()[0]["title"] == "저녁"
    c.patch(f"/api/plans/{pid}", json={"title": "늦은 저녁", "start_time": "19:00", "end_time": "20:00"})
    assert c.get(f"/api/plans/{pid}").json()["title"] == "늦은 저녁"
    c.delete(f"/api/plans/{pid}")
    assert c.get("/api/plans").json() == []
    say(c, "저녁 추천해줘")
    logs = c.get("/api/logs").json()
    assert logs and c.get(f"/api/logs/{logs[0]['session_id']}").json()
    assert c.delete(f"/api/logs/{logs[0]['session_id']}").status_code in (200, 204)
    say(c, "물 100")
    assert c.get("/api/export").json()["kitchen"]["daily"]
    assert c.delete("/api/data", params={"confirm": "삭제"}).status_code == 204
    assert state(c)["오늘 기록"] == {}


def test_cook_guide_servings_reflect(c):
    one = c.post("/api/guide", json={"title": "제육볶음", "servings": 1}).json()
    three = c.post("/api/guide", json={"title": "제육볶음", "servings": 3}).json()
    g1 = {x["이름"]: x["분량(g)"] for x in one["재료 합계"]}
    g3 = {x["이름"]: x["분량(g)"] for x in three["재료 합계"]}
    assert all(abs(g3[k] - g1[k] * 3) < 0.11 for k in g1)


def test_cook_records_even_when_fridge_lacks_ingredients(c):
    """조리 모드에서 본 레시피를 냉장고에 없던 재료로 만들어도 기록되고, 있는 재료만 차감된다."""
    say(c, "입고", name="두부", quantity=500, unit="g")
    say(c, "메뉴 김치 두부찌개")
    r = say(c, "조리 2인분 16분")
    assert r["남은 음식"] == {"김치 두부찌개": 2}
    assert "있는 만큼만 차감" in r["계획"]["안내"] and "김치" in r["계획"]["안내"]
    tofu = next(l for l in r["포장"] if l["item"] == "두부")
    assert tofu["grams"] < 500


def test_cook_beyond_stock_deducts_only_what_exists(c):
    """재고보다 많이 조리하면 소비기한이 남은 재고만 모두 쓰고, 지난 재고는 건드리지 않으며 모자란 양을 알린다."""
    import datetime as dt

    d = dt.date.today()
    say(c, "입고", name="두부", quantity=40, unit="g", expires=(d - dt.timedelta(days=1)).isoformat())
    say(c, "입고", name="두부", quantity=200, unit="g", expires=(d + dt.timedelta(days=2)).isoformat())
    say(c, "입고", name="달걀", quantity=120, unit="g")
    say(c, "메뉴 두부 달걀찜")
    r = say(c, "조리 3인분 15분")
    assert [(x["item"], x["grams"]) for x in r["포장"]] == [("두부", 40)]
    assert "두부" in r["계획"]["안내"] and "달걀" in r["계획"]["안내"]
