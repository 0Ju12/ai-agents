"""Regression coverage for the end-to-end kitchen, provider boundaries, and advanced agents."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
import app as api
import connections, food_tools, gateway
from agent_roles import Worker, assess, diagnose
from registry import Task
from storage import KitchenDB, RevisionConflict, today


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FRIDGE_MODE", raising=False)
    for key in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "GOOGLE_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)


def pantry(name, quantity, expiry=None):
    return api.run("입고", params={"name": name, "unit": "g", "quantity": quantity, "expires": expiry})


def test_measured_lots_expiry_fefo_and_atomic_shortage():
    d = today()
    pantry("두부", 40, (d - timedelta(days=1)).isoformat())
    pantry("두부", 90, d.isoformat())
    pantry("두부", 200, (d + timedelta(days=2)).isoformat())
    pantry("계란", 120)
    p = api.run("메뉴 두부 달걀찜")["계획"]
    assert p["예상 kcal"] == 148 and p["영양"]["protein_g"] == 14.4
    after = api.run("조리 2인분 14분")
    assert [(x["item"], x["grams"]) for x in after["포장"]] == [("두부", 40), ("두부", 90), ("달걀", 20)]
    eaten = api.run("섭취 두부 달걀찜")
    assert (
        eaten["남은 음식"] == {"두부 달걀찜": 1} and eaten["건강"]["totals"]["protein_g"]["value"] == 14.4
    )


def test_idempotency_concurrency_and_source_selection():
    c = TestClient(api.app)

    def water():
        return c.post("/api/chat", json={"message": "물 250", "request_id": "repeat"})

    with ThreadPoolExecutor(2) as ex:
        assert all(x.status_code == 200 for x in ex.map(lambda _: water(), range(2)))
    assert api.state()["오늘 기록"]["water_ml"] == 250
    assert c.post("/api/chat", json={"message": "물 500", "request_id": "repeat"}).status_code == 409
    snap = {"day": today().isoformat(), "water_ml": 1000, "protein_g": 50}
    api.run("건강연동", params=snap)
    api.run("건강연동", params=snap)
    s = api.state()
    assert s["건강"]["totals"]["water_ml"] == {"value": 1000, "source": "Health Connect"}
    assert s["오늘 기록"]["water_ml"] == 250
    with pytest.raises(ValueError):
        api.run("건강연동", params={"day": today().isoformat(), "sleep_hours": 25})
    db = KitchenDB()
    v, k = db.read("new")
    db.commit("new", v, k, {}, None, "")
    with pytest.raises(RevisionConflict):
        db.commit("new", v, k, {}, None, "")


def test_allergen_diet_feedback_week():
    api.run("추가 달걀, 두부")
    api.run("메뉴 두부 달걀찜")
    filtered = api.run(
        "설정",
        params={
            "avoid": ["대두"],
            "level": "중급",
            "body": "등",
            "gear": ["덤벨"],
            "targets": {"water_ml": 1900},
        },
    )
    assert "메뉴" not in filtered["계획"] and filtered["계획"]["제외 후보"][0]["사유"].endswith("두부")
    api.run("운동완료", params={"effort": "어려움", "minutes": 8, "body": "등"})
    assert "강도 조정" in api.state()["운동 계획"]["reason"]
    assert api.run("물 200")["건강"]["hints"][0]["remaining"] == 1700
    assert len(api.run("주간계획")["계획"]["주간"]) == 7


@pytest.mark.parametrize("title,settings", [
    ("소고기 미역국", {"diet": "식물성"}),
    ("연어 스테이크", {"diet": "식물성"}),
    ("김치전", {"avoid": ["밀"]}),
])
def test_food_restrictions_cover_expanded_catalog(title, settings):
    api.run("설정", params={**settings, "minutes": 120})
    result = api.run("메뉴 " + title)["계획"]
    assert not result.get("메뉴")
    assert result["제외 후보"][0]["사유"].startswith(("식물성 조건", "제외 식재료"))


def test_unverified_external_candidates_excluded_for_restricted_diet(monkeypatch):
    monkeypatch.setenv("FOODSAFETY_API_KEY", "fixture")
    lookup = Mock(return_value={"ok": True, "data": [
        {"id": "demo", "메뉴": "두부국", "재료·분량": "두부 100g, 새우 10g", "조리 순서": ["끓인다"]}
    ]})
    monkeypatch.setattr(food_tools, "call", lookup)
    base = {"lots": []}
    for settings in ({"diet": "식물성"}, {"avoid": ["갑각류"]}):
        assert api.korean_options({**base, **settings}, "2026-11-19", Mock(), "두부") == []
    lookup.assert_not_called()
    assert api.korean_options(base, "2026-11-19", Mock(), "두부")[0]["메뉴"] == "두부국"


def test_plans_calendar_and_deadline():
    c = TestClient(api.app)
    day = today().isoformat()

    def plan(start, end):
        return c.post(
            "/api/plans",
            json={"title": "저녁 일정", "start_time": start, "end_time": end, "trip_date": day},
        )

    one = plan("18:15", "19:00").json()["plan"]["id"]
    assert plan("18:20", "18:40").json()["overlaps"]
    assert plan("28:00", "28:30").status_code == 422
    assert c.patch("/api/plans/" + str(one), json={"end_time": "17:45"}).status_code == 422
    assert c.get("/api/plans/" + str(one)).json()["start_time"] == "18:15"
    for _ in range(2):
        assert api.run("일정등록 " + str(one))["계획"]["조회"]["ok"]
    assert len(api.run("일정조회 " + day)["계획"]["조회"]["data"]) == 1
    api.run("추가 달걀, 두부")
    p = api.run("시간대 " + day + " 18:00")["계획"]
    assert p["시간대"]["available"] == 15 and p["늦어도 조리 시작"] == "18:00"
    assert c.delete("/api/plans/" + str(one)).status_code == 204
    assert c.get("/api/plans/" + str(one)).status_code == 404


def test_private_households_and_deletion(monkeypatch):
    monkeypatch.setenv("FRIDGE_MODE", "server")
    clients = [TestClient(api.app, base_url="https://testserver") for _ in range(2)]
    for c in clients:
        assert c.get("/api/state").status_code == 200
    first, second = clients
    first.post("/api/chat", json={"message": "추가 두부"})
    assert second.get("/api/state").json()["냉장고"] == [] and second.get("/api/logs").json() == []
    assert (
        first.delete("/api/data?confirm=삭제").status_code == 204
        and first.get("/api/state").json()["냉장고"] == []
    )


def test_logger_and_worker_contract(monkeypatch):
    events = []

    def emit(kind, label, **payload):
        events.append({"name": label, "type": kind, "payload": payload})

    assert assess([])["status"] == "판정 불가"
    emit("plan", "작업", tools=["search"])
    emit("tool_call", "search", argument="tofu")
    emit("tool_call", "search", argument="tofu")
    emit("tool_call", "gyms", argument="A")
    for _ in range(4):
        emit("replan", "변경")
    a = assess(events)
    assert a["status"] == "이상" and len(a["warnings"]) == 3
    monkeypatch.setattr(gateway, "configured", lambda: True)
    chooser = Mock(
        return_value={"decision": "retry", "argument": "tofu", "role": "Planner", "action": "중복 제거"}
    )
    monkeypatch.setattr(gateway, "decide", chooser)
    diagnose({"status": "정상"}, emit)
    assert chooser.call_count == 0
    diagnose(a, emit)
    assert events[-1]["type"] == "diagnosis"
    calls = []

    def probe(tool, arg):
        calls.append((tool, arg))
        return {"ok": True, "data": [1]} if arg == "tofu" else {"ok": False, "error": "NO_RESULT"}

    monkeypatch.setattr(food_tools, "call", probe)
    worker = Worker(emit, lambda: {})
    t = Task(tool="search", argument="soy curd", fixed=False, purpose="대안 재료 검색")
    assert worker.perform(t).attempts == 2 and calls == [("search", "soy curd"), ("search", "tofu")]
    assert worker.perform(t.model_copy(update={"fixed": True})).decision == "escalate" and len(calls) == 2
    monkeypatch.setattr(food_tools, "call", lambda *_: {"ok": False, "error": "MISSING_KEY"})
    before = chooser.call_count
    worker.perform(t.model_copy(update={"argument": "b"}))
    assert before == chooser.call_count


def test_google_adapter_and_gms_routing(monkeypatch):
    import calendar_adapter as cal

    from fake_llm import FakeChat

    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    FakeChat.calls.clear()
    monkeypatch.setattr(gateway, "ChatOpenAI", FakeChat.factory(decide={"action": "추천", "minutes": 24}))
    out = api.run("오늘 쓸 수 있는 시간이 얼마인지 반영해줘")
    assert out["총 가용 시간"] == 24
    assert FakeChat.calls[0].kwargs["base_url"].startswith("https://gms.ssafy.io/")
    events = [
        {
            "id": "abc",
            "summary": "일정",
            "start": {"dateTime": "2026-11-20T08:00:00Z"},
            "end": {"dateTime": "2026-11-20T08:30:00Z"},
        }
    ]
    monkeypatch.setattr(cal, "google_call", lambda *args, **kw: {"items": events})
    assert cal.calendar("calendar_list", "2026-11-20", "google")["data"][0]["start"] == "17:00"


def test_provider_mapping_and_recipe_adoption(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "fixture")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "fixture")
    monkeypatch.setattr(
        connections,
        "request_json",
        lambda *a, **k: {
            "items": [
                {
                    "productId": "x",
                    "title": "<b>두부</b> 300g",
                    "lprice": "3000",
                    "link": "https://example.org/x",
                    "mallName": "검증",
                }
            ]
        },
    )
    api.run("설정", params={"budget_krw": 3500})
    result = api.run("쇼핑 두부")["계획"]
    assert result["자료"]["naver"]["data"][0]["예산 판정"] == "상품가 예산 이내"
    assert result["자료"]["coupang"]["error"] == "MISSING_KEY"
    monkeypatch.setattr(
        food_tools,
        "call",
        lambda *_: {
            "ok": True,
            "source": "식약처 검증 응답",
            "data": [{"id": "123", "메뉴": "검증 두부", "조리 순서": ["익히기"], "재료·분량": "두부 80g"}],
        },
    )
    api.run("레시피 두부")
    pantry("두부", 100)
    p = api.run("레시피저장", params={"id": "123", "minutes": 7, "grams": {"두부": 80}})["계획"]
    assert p["메뉴"] == "검증 두부 · 내 레시피" and p["예상 kcal"] == 61
    assert "검증 두부 · 내 레시피" in api.state()["메뉴 목록"]


def test_mobile_comma_entry_and_natural_sentence():
    first = api.run("입고", params={"name": "두부, 계란"})
    assert first["냉장고"] == ["달걀", "두부"]
    s = api.run("냉장고에 두부와 달걀이 있어. 20분 안에 뭘 먹을까?", session_id="sentence")
    assert s["냉장고"] == ["달걀", "두부"] and s["총 가용 시간"] == 20
    assert not api.run("냉장고에 달걀이 있어?", session_id="question")["냉장고"]


def test_cart_to_pantry_and_unit_prices():
    from domain.shopping import comparable

    api.run("메뉴 두부 달걀찜")
    c = api.run("장바구니담기", params={"servings": 2})["장바구니"]
    assert c["두부"]["grams"] == 200 and c["달걀"]["grams"] == 100
    assert api.run("구매완료 두부", params={"quantity": 40})["장바구니"]["두부"]["grams"] == 160
    assert "두부" not in api.run("구매완료 두부", params={"quantity": 200})["장바구니"]
    assert comparable("두부 100g 2팩", 350, 1500)["필요량 구매 표시가(원)"] == 3000
    assert comparable("두부 200g/300g 선택", 80, 2500) == {}


def test_history_legacy_migration(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    old = {"stock": ["두부"], "minutes": 18, "goal": "체력", "leftovers": {"옛 메뉴": 1}, "records": []}
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY,state TEXT,result TEXT)")
        c.execute("INSERT INTO runs(state) VALUES(?)", (json.dumps(old),))
    reply = api.run("추천", db_path=path)
    assert reply["포장"][0]["grams"] is None and reply["남은 음식"] == {"옛 메뉴": 1}
    assert api.run("섭취 옛 메뉴", db_path=path)["건강"]["totals"]["kcal"]["value"] is None


def test_authenticated_connector_contracts(monkeypatch):
    from datetime import datetime, timezone
    from urllib.parse import urlsplit, parse_qs

    for key in (
        "KAKAO_REST_API_KEY",
        "COUPANG_ACCESS_KEY",
        "COUPANG_SECRET_KEY",
        "YOUTUBE_API_KEY",
        "IG_USER_ID",
        "IG_ACCESS_TOKEN",
    ):
        monkeypatch.setenv(key, "test-only")
    stamp = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    def transport(url, headers=None, **kwargs):
        u = urlsplit(url)
        if u.hostname == "dapi.kakao.com":
            assert headers["Authorization"] == "KakaoAK test-only"
            return {
                "documents": [
                    {
                        "id": "g",
                        "place_name": "테스트 체육관",
                        "address_name": "검증동",
                        "place_url": "https://example.org/g",
                    }
                ]
            }
        if u.hostname == "api-gateway.coupang.com":
            assert "signature=" in headers["Authorization"] and "test-only" not in url
            return {
                "rCode": "0",
                "data": {
                    "productData": [
                        {
                            "productId": 1,
                            "productName": "두부 300g",
                            "productPrice": 2200,
                            "productUrl": "https://example.org/b",
                        }
                    ]
                },
            }
        if u.path.endswith("/search"):
            assert "publishedAfter" in parse_qs(u.query)
            return {"items": [{"id": {"videoId": "sample"}}]}
        if u.path.endswith("/videos"):
            return {
                "items": [
                    {
                        "id": "sample",
                        "snippet": {"publishedAt": stamp, "title": "조리 시연", "channelTitle": "시험"},
                        "statistics": {"viewCount": "100"},
                    }
                ]
            }
        if u.path.endswith("ig_hashtag_search"):
            assert headers["Authorization"] == "Bearer test-only"
            return {"data": [{"id": "t"}]}
        if u.path.endswith("recent_media"):
            return {
                "data": [
                    {
                        "caption": "검증 영상",
                        "timestamp": stamp,
                        "permalink": "https://example.org/post",
                        "comments_count": 3,
                    }
                ]
            }
        raise AssertionError(u.hostname)

    monkeypatch.setattr(connections, "request_json", transport)
    for name in ("gyms", "coupang", "youtube", "instagram"):
        r = connections.lookup(name, "두부")
        assert r["ok"] and r["data"][0]["url"] and "test-only" not in json.dumps(r)
    assert connections.youtube("두부")["data"][0]["views_per_day"] == 50
    assert connections.instagram("두부")["data"][0]["likes"] is None


def test_oauth_state_is_one_time_and_household_scoped(tmp_path, monkeypatch):
    import oauth_calendar
    from io import BytesIO
    from urllib.parse import urlparse, parse_qs

    monkeypatch.setenv("FRIDGE_MODE", "server")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://testserver/api/calendar/callback")
    client, other = [TestClient(api.app, base_url="https://testserver") for _ in range(2)]
    client.get("/api/state")
    other.get("/api/state")
    redirect = client.get("/api/calendar/connect", follow_redirects=False)
    grant = parse_qs(urlparse(redirect.headers["location"]).query)
    assert grant["code_challenge_method"] == ["S256"]
    state = grant["state"][0]
    monkeypatch.setattr(
        oauth_calendar, "urlopen", lambda *_a, **_k: BytesIO(b'{"refresh_token":"unit-refresh"}')
    )
    callback = "/api/calendar/callback?state=" + state + "&code=unit"
    assert other.get(callback, follow_redirects=False).status_code == 400
    assert client.get(callback, follow_redirects=False).status_code == 303
    assert client.get(callback, follow_redirects=False).status_code == 400
    assert client.get("/api/calendar/status").json()["provider"] == "google"
    assert other.get("/api/calendar/status").json()["provider"] == "local"
    assert "unit-refresh" not in client.get("/api/export").text
    client.delete("/api/calendar/connection")
    assert client.get("/api/calendar/status").json()["provider"] == "local"
