"""상황 문장 → 자동 진행(추천 후보·메뉴 확정·장바구니·영상·조리 모드), 예시 냉장고, 직접 붙인 영상 링크."""

import pytest
from fastapi.testclient import TestClient

import app as api
import autopilot
import gateway
from fake_llm import FakeChat


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    for key in ("FRIDGE_MODE", "FRIDGE_DEMO", "GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY", "IG_USER_ID", "IG_ACCESS_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_demo_pantry_only_once(monkeypatch):
    client = TestClient(api.app)
    assert client.get("/api/state").json()["데모 필요"] is False  # FRIDGE_DEMO 꺼짐
    monkeypatch.setenv("FRIDGE_DEMO", "1")
    assert client.get("/api/state").json()["데모 필요"] is True
    r = client.post("/api/demo", json={}).json()
    assert len(r["포장"]) == len(autopilot.DEMO_LOTS) and all(l["expires"] for l in r["포장"])
    api.run("삭제 " + ", ".join(n for n, *_ in autopilot.DEMO_LOTS))
    assert client.get("/api/state").json()["데모 필요"] is False  # 비워도 다시 채우지 않는다


def test_situation_runs_agent_and_ranks_expiring_first():
    api.run("데모")
    p = api.run("퇴근했는데 20분밖에 없어. 단백질 위주로 먹고 싶어")["계획"]
    assert [d["작업"] for d in p["자동 진행"]] == ["메뉴 확정", "영상·게시물 찾기", "조리 모드 준비"]
    top = p["추천 후보"][0]
    assert top["메뉴"] == p["확정 메뉴"] and "기한 임박 두부 D-1" in top["근거"]
    assert all(x["조리시간(분)"] <= 20 for x in p["추천 후보"])
    assert p["메뉴"] == top["메뉴"]  # 확정 메뉴로 계획이 바뀐다


def test_servings_drive_cart_and_no_buy_words():
    api.run("데모")
    r = api.run("두부 달걀찜 4명이서 먹고 싶어")
    assert r["계획"]["추천 후보"][0]["메뉴"] == "두부 달걀찜" and r["계획"]["인분"] == 4
    assert r["장바구니"] == {"두부": {"grams": 100.0, "meal": "두부 달걀찜", "auto": True}}  # 4인분 400g - 보유 300g, 자동으로 담은 표시
    cart = next(d for d in r["계획"]["자동 진행"] if d["작업"] == "장바구니 담기")
    assert cart["되돌리기"] == ["장바구니삭제 두부"]
    api.run("장바구니삭제 두부")
    r = api.run("두부 달걀찜 4명이서 먹을건데 있는 재료로만")
    assert r["장바구니"] == {} and "장바구니 담기" not in [d["작업"] for d in r["계획"]["자동 진행"]]


def test_model_can_only_pick_allowed_actions(monkeypatch):
    api.run("데모")
    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    monkeypatch.setattr(
        gateway, "ChatOpenAI",
        FakeChat.factory(decide={"action": "추천"}, plan={"AutoPlan": {"actions": ["메뉴확정"], "servings": 2, "reason": "메뉴만"}}, answer="두부 달걀찜으로 정했어요."),
    )
    p = api.run("오늘 저녁 뭐 먹지")["계획"]
    assert [d["작업"] for d in p["자동 진행"]] == ["메뉴 확정"] and p["인분"] == 2
    assert p["판단 방법"] == "모델(코드 검증)" and p["답변"] == "두부 달걀찜으로 정했어요."


def test_pasted_links_play_without_keys():
    assert autopilot.parse_link("https://youtu.be/abcdefghijk")["id"] == "abcdefghijk"
    assert autopilot.parse_link("https://www.youtube.com/shorts/abcdefghijk?feature=x")["id"] == "abcdefghijk"
    assert autopilot.parse_link("https://www.instagram.com/reels/C1aBcDeFgH/")["url"] == "https://www.instagram.com/reel/C1aBcDeFgH/"
    assert autopilot.parse_link("https://evil.example/watch?v=abcdefghijk") is None
    assert autopilot.parse_link("javascript:alert(1)") is None
    api.run("영상링크", params={"menu": "두부 달걀찜", "url": "https://www.youtube.com/watch?v=abcdefghijk"})
    api.run("영상링크", params={"menu": "두부 달걀찜", "url": "https://www.instagram.com/p/C1aBcDeFgH/"})
    with pytest.raises(ValueError):
        api.run("영상링크", params={"menu": "두부 달걀찜", "url": "http://youtu.be/abcdefghijk"})
    m = TestClient(api.app).post("/api/guide/media", json={"menu": "두부 달걀찜", "steps": ["a", "b"]}).json()
    assert m["youtube"]["ok"] and m["youtube"]["data"][0]["id"] == "abcdefghijk" and m["youtube"]["data"][0]["step_starts"] == [None, None]
    assert m["instagram"]["ok"] and m["instagram"]["data"][0]["url"].endswith("/p/C1aBcDeFgH/")


def test_model_reply_comes_with_plan_to_save_a_call(monkeypatch):
    """자동 진행 판단에서 문장까지 받으면 별도 답변 호출을 하지 않는다(해석 1 + 판단 1 = 2회)."""
    api.run("데모")
    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    FakeChat.calls.clear()
    monkeypatch.setattr(
        gateway, "ChatOpenAI",
        FakeChat.factory(decide={"action": "추천"}, plan={"AutoPlan": {"actions": ["메뉴확정"], "message": "두부가 **내일까지라** 두부 요리로 골랐어요."}}, answer="쓰이면 안 되는 문장"),
    )
    p = api.run("오늘 저녁 뭐 먹지")["계획"]
    assert p["답변"] == "두부가 내일까지라 두부 요리로 골랐어요."
    assert len(FakeChat.calls) == 2


def test_workout_sentence_is_not_a_gym_search():
    p = api.run("어깨 운동 30분 하고 싶어")["계획"]
    r = p["운동 루틴"]
    assert r["body"] == "어깨" and r["minutes"] == 30 and len(r["exercises"]) >= 2
    assert api.run("초보 하체 루틴 20분")["계획"]["운동 루틴"]["level"] == "초보"
    assert "어느 동네" in api.run("헬스장 찾아줘")["계획"]["안내"]


def test_menu_words_categories_and_light_meals():
    api.run("데모")
    assert api.run("김치찌개 먹고 싶어")["계획"]["추천 후보"][0]["메뉴"] == "돼지고기 김치찌개"
    r = api.run("파스타 해먹고 싶어 둘이서")
    assert "파스타" in r["계획"]["추천 후보"][0]["메뉴"] and r["장바구니"]["파스타"]["grams"] == 180
    assert set(api.run("배고파")["장바구니"]) == set()  # 다른 메뉴로 바뀌면 자동으로 담았던 재료는 뺀다
    meat = api.run("고기 먹고 싶어")["계획"]["추천 후보"]
    assert all(any(k in x["메뉴"] for k in ("고기", "닭", "불고기", "제육")) for x in meat)
    light = api.run("다이어트 중인데 저녁")["계획"]
    kcal = [x["예상 kcal"] for x in light["추천 후보"]]
    assert kcal == sorted(kcal) and "열량" in light["판단 이유"]
    assert api.run("두부 사고 싶어")["계획"]["검색어"] == "두부"
    assert "물 500mL를 기록" in api.run("물 500ml")["계획"]["안내"]
    assert api.run("안녕")["계획"]["안내"].startswith("안녕하세요")


def test_named_menu_over_time_limit_adjusts_time_with_undo():
    api.run("데모")
    api.run("퇴근했는데 20분밖에 없어. 단백질 위주로 먹고 싶어")
    p = api.run("김치찌개 먹고 싶어")["계획"]
    assert p["추천 후보"][0]["메뉴"] == "돼지고기 김치찌개" and p["메뉴"] == "돼지고기 김치찌개"
    step = p["자동 진행"][0]
    assert step["작업"] == "가용 시간 조정" and step["되돌리기"] == "시간 20"


def test_exercise_photos_are_served_from_allowed_source():
    from fastapi.testclient import TestClient
    import media

    api.run("하체 운동 20분 중급")
    g = TestClient(api.app).post("/api/workout/guide", json={}).json()
    squat = next(s for s in g["단계"] if s["name"] == "맨몸 스쿼트")
    assert len(squat["photos"]) == 2 and squat["photos"][0].startswith("/api/media?u=") and "퍼블릭 도메인" in squat["credit"]
    assert media.allowed("https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/Plank/0.jpg")
    assert not media.allowed("https://raw.githubusercontent.com/evil/repo/main/x.jpg")
    assert not media.allowed("https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/../../x")
