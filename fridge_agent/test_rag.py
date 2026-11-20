"""F3022 RAG 검색 Tool: 도구 선택, 근거·출처, 색인 없음(NO_INDEX), 결과 없음, 모델 답변의 근거 사용."""

import pytest

import app as api
import gateway
import knowledge
from fake_llm import FakeChat


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDGE_DATA_DIR", str(tmp_path))
    for key in ("FRIDGE_MODE", "GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY", "RAG_EMBED"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("question,title", [
    ("단백질 하루 권장량이 얼마야?", "단백질 하루 권장섭취량"),
    ("물은 하루에 얼마나 마셔야 해?", "하루 수분 섭취량"),
    ("냉동 고기 어떻게 해동해?", "냉동 식품 안전한 해동"),
    ("잠은 몇 시간 자야해", "성인 적정 수면 시간"),
    ("일주일에 운동 얼마나 해야돼?", "성인 권장 신체활동량"),
])
def test_retrieval_finds_the_right_guide(question, title):
    r = knowledge.search(question)
    assert r["ok"] and r["data"][0]["title"] == title and r["data"][0]["url"].startswith("https://")


def test_agent_selects_rag_for_questions_apis_cannot_answer():
    out = api.run("단백질 하루 권장량이 얼마야?")
    calls = [e["name"] for e in out["추적"] if e["type"] == "tool_call"]
    assert calls == ["knowledge"]
    p = out["계획"]
    assert p["근거 문서"][0]["source"].startswith("보건복지부") and "65g" in p["답변"] and "출처" in p["답변"]
    assert "저녁" not in str(calls) and api.run("저녁 추천해줘")["계획"].get("근거 문서") is None  # 메뉴 요청은 RAG 로 가지 않는다


def test_unrelated_question_and_missing_index(monkeypatch):
    assert knowledge.search("오늘 주가 어때?")["error"] == "NO_RESULT"
    assert "찾지 못했어요" in api.run("오늘 날씨 어때?")["계획"]["안내"]

    class Broken:
        def __init__(self, *a, **k):
            raise OSError("disk")

    import chromadb

    monkeypatch.setattr(chromadb, "PersistentClient", Broken)
    assert knowledge.search("단백질 권장량은?") == {"ok": False, "error": "NO_INDEX"}
    assert api.run("단백질 권장량은 얼마야?")["계획"]["오류"] == "NO_INDEX"


def test_index_rebuilds_when_documents_change(monkeypatch, tmp_path):
    knowledge.search("소비기한이 뭐야")
    docs = knowledge.docs() + [{"id": "x-test", "title": "시험 문서 바나나보관", "topic": "시험", "text": "바나나보관 시험 문단입니다.", "source": "시험", "url": "https://example.org", "keywords": "바나나보관"}]
    monkeypatch.setattr(knowledge, "docs", lambda: docs)
    assert knowledge.search("바나나보관 시험")["data"][0]["id"] == "x-test"


def test_model_answer_is_built_from_evidence(monkeypatch):
    monkeypatch.setenv("GMS_KEY", "unit-test-value")
    monkeypatch.setenv("GMS_PROVIDER", "openai")
    monkeypatch.setattr(gateway, "ChatOpenAI", FakeChat.factory(decide={"action": "질문", "argument": "카페인 하루 얼마까지?"}, answer="식약처는 성인 카페인을 하루 400mg 이하로 안내해요."))
    p = api.run("카페인 하루에 얼마까지 괜찮아?")["계획"]
    assert p["답변"].startswith("식약처는") and p["근거 문서"][0]["title"] == "카페인 하루 최대 섭취 권고량"
