import pytest


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    """공통 계층 테스트는 외부 API·모델을 부르지 않는다."""
    for env in ("GMS_KEY", "GMS_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
