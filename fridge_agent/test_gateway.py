from urllib.error import HTTPError

import pytest
from pydantic import BaseModel, ValidationError

import gateway


class Result(BaseModel):
    name: str


@pytest.fixture
def gms(monkeypatch):
    monkeypatch.setenv("GMS_KEY", "fixture")
    monkeypatch.delenv("GMS_PROVIDER", raising=False)
    monkeypatch.delenv("GMS_ANTHROPIC_MODEL", raising=False)
    # Existing OpenAI settings must not change the Anthropic route or model.
    monkeypatch.setenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    monkeypatch.setenv("GMS_MODEL", "gpt-6.1-sol")


def test_anthropic_text_request(monkeypatch, gms):
    def request(url, payload, headers, *, timeout):
        assert url == "https://gms.ssafy.io/gmsapi/api.anthropic.com/v1/messages"
        assert headers == {"x-api-key": "fixture", "anthropic-version": "2023-06-01"}
        assert payload["model"] == "claude-opus-5-5" and payload["max_tokens"] == 2048
        assert payload["system"].startswith("한끼 셰프")
        assert payload["messages"] == [{"role": "user", "content": '{"이름": "두부"}'}]
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "두부 요리를 추천해요."}]}

    monkeypatch.setattr(gateway, "request_json", request)
    assert gateway.write("셰프", "답변해 주세요.", {"이름": "두부"}) == "두부 요리를 추천해요."


def test_anthropic_tools_and_photo(monkeypatch, gms):
    seen = []

    def request(url, payload, headers, *, timeout):
        seen.append(payload)
        assert payload["tool_choice"] == {"type": "tool", "name": "return_result"}
        return {"stop_reason": "tool_use", "content": [
            {"type": "tool_use", "name": "return_result", "input": {"name": "달걀"}},
        ]}

    monkeypatch.setattr(gateway, "request_json", request)
    assert gateway.decide("Planner", "", {}) == {"name": "달걀"}
    assert gateway.structured("Planner", "", {}, Result).name == "달걀"
    assert gateway.see("사진", "", "data:image/png;base64,AA==", Result).name == "달걀"
    assert seen[-1]["tools"][0]["input_schema"] == Result.model_json_schema()
    assert seen[-1]["messages"][0]["content"][0]["source"] == {
        "type": "base64", "media_type": "image/png", "data": "AA==",
    }

    seen.clear()
    monkeypatch.setattr(gateway, "request_json", lambda *a, **k: {"content": [
        {"type": "tool_use", "name": "return_result", "input": {}},
    ]})
    with pytest.raises(ValidationError):
        gateway.structured("Planner", "", {}, Result)


def test_anthropic_hides_provider_error_details(monkeypatch, gms):
    def failure(*args, **kwargs):
        raise HTTPError("https://example.test/?key=secret", 401, "secret", {}, None)

    monkeypatch.setattr(gateway, "request_json", failure)
    with pytest.raises(OSError, match=r"^GMS 모델 호출 실패: HTTPError$"):
        gateway.write("셰프", "", {})
