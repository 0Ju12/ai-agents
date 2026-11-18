import pytest

from backend.config import KEY_ENV


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    """테스트는 외부 API 를 부르지 않는다 — 모든 키를 비워 둔다."""
    for env in KEY_ENV.values():
        monkeypatch.setenv(env, "")
