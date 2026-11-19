"""모델 계획(Planner) · 앞 단계 결과 전달 · 응답 문장 — 대역 모델(FakeChat)로 키 없이 검증한다."""

import pytest
import app as api
import food_tools
import gateway
from agent_roles import Planner, recipe_ingredients
from fake_llm import FakeChat

RECIPE = {
    "ok": True,
    "source": "식품안전나라",
    "data": [{"id": "1", "메뉴": "김치찌개", "재료·분량": "●주재료 : 김치 200g, 돼지고기 100g, 두부 1/2모\n●양념 : 고춧가루 약간"}],
}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FRIDGE_MODE", raising=False)
    for key in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "PLANNER_LLM", "ANSWER_LLM"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_call(tool, argument):
        seen.append((tool, argument))
        if tool == "kr_recipe":
            return RECIPE
        return {"ok": True, "source": tool, "data": [{"id": argument, "title": argument + " 상품", "price_krw": 5000}]}

    monkeypatch.setattr(food_tools, "call", fake_call)
    return seen


def with_model(monkeypatch, **script):
    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    FakeChat.calls.clear()
    monkeypatch.setattr(gateway, "ChatOpenAI", FakeChat.factory(**script))


def test_recipe_ingredients_parses_foodsafety_text():
    assert recipe_ingredients(RECIPE["data"][0]["재료·분량"]) == ["김치", "돼지고기", "두부", "고춧가루"]


def test_model_plans_recipe_then_shopping_for_missing_items(monkeypatch, calls):
    api.run("추가 두부, 고춧가루")
    with_model(
        monkeypatch,
        decide={"action": "레시피", "argument": "김치찌개"},
        plan={
            "steps": [
                {"tool": "naver", "argument": "$부족재료", "purpose": "부족한 재료 가격 비교"},
                {"tool": "rm_rf", "argument": "x"},  # 등록되지 않은 도구는 코드가 버린다
            ],
            "reason": "레시피 재료를 확인한 뒤 없는 재료만 장보기",
        },
        answer="김치와 돼지고기가 없어 네이버 상품을 찾았습니다.",
    )
    out = api.run("김치찌개 먹고 싶은데 뭐 사야 해?")
    # 레시피 → (재고 비교) → 없는 재료만 쇼핑. 두부·고춧가루는 이미 있다.
    assert calls == [("kr_recipe", "김치찌개"), ("naver", "김치"), ("naver", "돼지고기")]
    assert out["계획"]["답변"].startswith("김치와 돼지고기")
    assert [x["입력"] for x in out["계획"]["추가 조회"]] == ["김치", "돼지고기"]


def test_explicit_command_and_no_model_use_rule_plan(monkeypatch, calls):
    tasks, reason = Planner.plan("레시피", "김치찌개", request="김치찌개 사야 해?")
    assert [t.tool for t in tasks] == ["kr_recipe"] and "요청" in reason  # 모델 키 없음 → 규칙
    with_model(monkeypatch, plan={"steps": [{"tool": "naver", "argument": "김치"}]})
    out = api.run("레시피 김치찌개")  # 명령어 입력은 모델 계획·문장 생성 없이 바로 실행
    assert calls == [("kr_recipe", "김치찌개")] and "답변" not in out["계획"]


def test_model_failure_falls_back_to_rule_plan(monkeypatch, calls):
    with_model(monkeypatch, decide={"action": "레시피", "argument": "김치찌개"})

    def broken(self, schema):
        raise RuntimeError("upstream https://gms.ssafy.io/?key=secret")

    monkeypatch.setattr(FakeChat, "with_structured_output", broken)
    out = api.run("김치찌개 레시피 알려줘")
    assert calls == [("kr_recipe", "김치찌개")]
    assert "secret" not in str(out)
