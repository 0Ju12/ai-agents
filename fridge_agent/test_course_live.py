"""2·3일차 실계정 점검. 환경 설정이 있는 경우에만 실행한다."""

import os

import pytest

import gateway
from agent_roles import Planner
from calendar_adapter import calendar, token_file
from storage import local_store, today
from workflow import answer


pytestmark = pytest.mark.skipif(os.getenv("HANKKI_COURSE_LIVE") != "1", reason="실계정 점검 비활성")


def require_gms():
    if not (os.getenv("GMS_KEY") or os.getenv("GMS_API_KEY")):
        pytest.skip("GMS 키 미설정")


def test_gms_same_question_twice():
    require_gms()
    question = "지금 내 냉장고에 달걀이 몇 개 있는지 알려줘."
    for attempt in (1, 2):
        reply = gateway.write("실습", "질문에 짧게 답한다.", {"질문": question})
        assert reply
        print(f"{attempt}차 응답 · {reply}")


def test_live_planner_and_answer():
    require_gms()
    events = []

    def emit(kind, name, **payload):
        events.append((kind, payload.get("method")))

    question = "달걀찜에 부족한 재료를 장보고 싶어."
    tasks, _ = Planner.plan("레시피", "달걀찜", request=question, emit=emit)
    assert tasks and ("llm_decision", "model") in events
    result = answer(question, {"메뉴": "달걀찜", "부족 재료": ["달걀"]}, emit)
    assert result.get("답변") and events.count(("llm_decision", "model")) == 2


def test_google_calendar_read():
    if not os.getenv("FRIDGE_DATA_DIR") or not token_file().is_file():
        pytest.skip("연결된 Google 캘린더 데이터 경로 미설정")
    result = calendar("calendar_list", today().isoformat(), "google")
    assert result.get("ok") and isinstance(result.get("data"), list)


def test_google_calendar_register_and_read_back():
    plan_id = os.getenv("HANKKI_CHECK_PLAN_ID")
    if not plan_id or not os.getenv("FRIDGE_DATA_DIR") or not token_file().is_file():
        pytest.skip("Google 테스트 일정 등록용 데이터 경로 또는 계획 ID 미설정")
    assert local_store().get_plan(int(plan_id)), "테스트용 계획 ID를 확인하세요."
    registered = calendar("calendar_register", plan_id, "google")
    assert registered.get("ok")
    event = registered["data"]
    listed = calendar("calendar_list", event["day"], "google")
    assert listed.get("ok")
    assert any(row["id"] == event["id"] and row["start"] == event["start"]
               and row["end"] == event["end"] for row in listed["data"])
