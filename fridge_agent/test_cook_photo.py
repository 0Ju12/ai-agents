"""조리 모드 · 사진 기록 · 바코드 — 대역 모델(FakeChat)과 고정 제공처 응답으로 검증한다."""

import base64

import pytest
from fastapi.testclient import TestClient

import app as api
import cook_guide
import food_tools
import gateway
import korean_food
from fake_llm import FakeChat

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 400).decode()


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FRIDGE_MODE", raising=False)
    for key in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def client():
    return TestClient(api.app)


def with_model(monkeypatch, **script):
    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    monkeypatch.setattr(gateway, "ChatOpenAI", FakeChat.factory(**script))


def test_rule_parsing_helpers():
    assert cook_guide.clean("1. 양파를 채 썬다.a") == "양파를 채 썬다."
    assert cook_guide.detect_action("냄비에 물을 붓고 5분간 끓인다") == "끓이기"
    assert cook_guide.detect_action("두부를 넣는다") == "넣기"
    assert cook_guide.timer_seconds("중불에서 3분 30초 볶는다") == 210
    assert cook_guide.timer_seconds("맛있게 볶는다") is None
    assert korean_food.secure("http://www.foodsafetykorea.go.kr/uploadimg/cook/1.png").startswith("https://")
    assert korean_food.secure("http://evil.example/x.png") is None


def test_local_guide_scales_grams_without_model(client):
    api.run("추가 두부")
    g = client.post("/api/guide", json={"title": "두부 달걀찜", "servings": 2}).json()
    assert g["판단 방법"] == "규칙" and len(g["단계"]) == 5  # 재료 준비 + 원문 3단계 + 완성·보관
    assert g["단계"][0]["종류"] == "prep" and g["단계"][-1]["종류"] == "finish"
    assert any("두부" in line and "모)" in line for line in g["단계"][0]["계량"])  # 두부 200g(⅔모)
    tofu = next(x for x in g["재료 합계"] if x["이름"] == "두부")
    assert tofu["분량(g)"] == 200 and tofu["보유"] is True
    assert [c["애니메이션"] for c in g["단계"]][2] == "steam"  # 찜기에 넣으세요 → 찌기
    assert g["단계"][2]["익힘 기준"] and g["단계"][2]["불 세기"] == "센불" and g["단계"][2]["불 세기 권장"]
    assert any(e["type"] == "node_start" for e in g["추적"])
    assert client.post("/api/guide", json={"title": "없는 메뉴"}).status_code == 422


def test_external_guide_uses_step_photos_and_validates_model(monkeypatch, client):
    recipe = {
        "ok": True,
        "source": "식품안전나라 COOKRCP01",
        "data": [
            {
                "id": "77",
                "메뉴": "김치찌개",
                "재료·분량": "●주재료 : 김치 200g, 돼지고기 100g, 두부 1/2모",
                "조리 순서": ["1. 김치와 돼지고기를 볶는다.a", "2. 물을 붓고 10분 끓인다.b", "3. 두부를 올려 마무리한다.c"],
                "단계 사진": ["https://www.foodsafetykorea.go.kr/uploadimg/cook/77_1.png", None, None],
                "대표 사진": None,
            }
        ],
    }
    monkeypatch.setattr(food_tools, "call", lambda tool, arg: recipe)
    api.run("레시피 김치찌개")
    with_model(
        monkeypatch,
        plan={"GuideDraft": {"steps": [{"index": 2, "action": "넣기", "ingredients": ["두부", "랍스터"], "tip": ""}]}},
    )
    g = client.post("/api/guide", json={"recipe_id": "77"}).json()
    steps = g["단계"][1:-1]  # 앞뒤 재료 준비·완성 단계를 뺀 원문 단계
    assert steps[0]["사진"] and steps[0]["동작"] == "볶기"
    assert steps[1]["타이머(초)"] == 600
    assert [x["이름"] for x in steps[2]["재료"]] == ["두부"]  # 목록에 없는 '랍스터'는 버린다
    assert g["판단 방법"].startswith("규칙 + 모델")


def test_photo_requires_valid_image_and_key(client):
    assert client.post("/api/photo", json={"kind": "meal", "image": "data:text/plain;base64," + "A" * 200}).status_code == 422
    r = client.post("/api/photo", json={"kind": "meal", "image": JPEG}).json()
    assert r["ok"] is False and r["error"] == "MISSING_KEY"


def test_meal_photo_candidates_then_confirmed_intake(monkeypatch, client):
    with_model(monkeypatch, plan={"Sight": {"items": [{"name": "계란", "grams": 100, "confidence": 0.9}, {"name": "외계 음식", "grams": 50}]}})
    r = client.post("/api/photo", json={"kind": "meal", "image": JPEG}).json()
    assert [x["name"] for x in r["후보"]] == ["달걀", "외계 음식"]
    assert r["예상 영양"]["미확인"] == ["외계 음식"]  # 참조가 없으면 지어내지 않는다
    assert any(e["name"] == "vision" for e in r["추적"])
    out = api.run("사진식사", params={"items": [{"name": "달걀", "grams": 100}]})
    assert out["건강"]["totals"]["protein_g"]["value"] == 12.6
    with pytest.raises(ValueError):
        api.run("사진식사", params={"items": [{"name": "달걀", "grams": 0}]})


def test_fridge_photo_then_register(monkeypatch, client):
    with_model(monkeypatch, plan={"Sight": {"items": [{"name": "두부", "count": 1}, {"name": "양파", "count": 2}]}})
    r = client.post("/api/photo", json={"kind": "fridge", "image": JPEG}).json()
    names = [x["name"] for x in r["후보"]]
    out = api.run("입고", params={"name": ", ".join(names)})
    assert set(out["냉장고"]) >= {"두부", "양파"} or {l["item"] for l in out["포장"]} >= {"두부", "양파"}


def test_barcode_lookup(monkeypatch, client):
    assert client.get("/api/barcode/12ab").status_code == 422
    monkeypatch.setattr(food_tools, "call", lambda tool, code: {"ok": True, "data": {"product": "국산콩 두부", "kcal": 84}})
    assert client.get("/api/barcode/8801234567890").json()["data"]["product"] == "국산콩 두부"
