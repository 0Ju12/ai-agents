"""물·영양제 알림: 등록·문장 해석·보낼지 판정(진도·복용 여부)·Android 예약용 목록."""

import pytest
from fastapi.testclient import TestClient

import app as api
import reminders


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    for key in ("FRIDGE_MODE", "GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_sentences_become_reminders():
    assert reminders.from_text("물 2시간마다 알려줘") == {"kind": "water", "every_min": 120, "start": "09:00", "end": "21:00"}
    assert reminders.from_text("비타민D 아침 9시랑 저녁 9시에 알려줘")["times"] == ["09:00", "21:00"]
    assert reminders.from_text("오메가3 점심에 챙겨줘")["times"] == ["12:30"]
    assert reminders.from_text("물 250") is None  # 알림 요청이 아니면 기존 명령 그대로
    api.run("비타민D 아침 9시랑 저녁 9시에 알려줘")
    api.run("물 90분마다 알려줘")
    items = TestClient(api.app).get("/api/reminders").json()["items"]
    assert [(x["kind"], x["title"]) for x in items] == [("supplement", "비타민D"), ("water", "물 마시기")]
    assert items[1]["slots"][:3] == ["09:00", "10:30", "12:00"]


def test_water_only_when_behind_pace():
    api.run("알림추가", params={"kind": "water", "start": "09:00", "end": "21:00", "every_min": 120, "cup_ml": 250})
    c = TestClient(api.app)
    due = c.get("/api/reminders/due", params={"now": "13:03"}).json()["due"]
    assert due[0]["kind"] == "water" and due[0]["action"]["message"] == "물 250"
    assert "500mL" in due[0]["body"]  # 1,500mL 목표 · 13시 진도 500mL
    api.run("물 600")
    assert c.get("/api/reminders/due", params={"now": "13:03"}).json()["due"] == []  # 진도보다 앞섬
    assert c.get("/api/reminders/due", params={"now": "13:20"}).json()["due"] == []  # 알림 시각이 아님


def test_supplement_skips_after_taken_and_toggle():
    api.run("알림추가", params={"kind": "supplement", "name": "비타민D", "dose": "1정", "times": ["09:00", "21:00"]})
    c = TestClient(api.app)
    rid = c.get("/api/reminders").json()["items"][0]["id"]
    due = c.get("/api/reminders/due", params={"now": "09:05"}).json()["due"]
    assert due[0]["title"] == "비타민D 드실 시간이에요" and "1정" in due[0]["body"]
    state = api.KitchenDB().read("default")[1]
    daily = state["daily"].setdefault(api.today().isoformat(), {})
    reminders.take(state, daily, rid, "09:10")
    assert reminders.due(state, daily, "09:05") == []
    assert [x["title"] for x in reminders.due(state, daily, "21:01")] == ["비타민D 드실 시간이에요"]
    api.run("알림토글 " + rid)
    assert c.get("/api/reminders/due", params={"now": "21:01"}).json()["due"] == []


def test_invalid_reminders_are_rejected():
    for params in (
        {"kind": "water", "start": "21:00", "end": "09:00"},
        {"kind": "water", "every_min": 5},
        {"kind": "supplement", "name": "", "times": ["09:00"]},
        {"kind": "supplement", "name": "비타민", "times": ["25:00"]},
        {"kind": "alarm"},
    ):
        with pytest.raises(ValueError):
            api.run("알림추가", params=params)
