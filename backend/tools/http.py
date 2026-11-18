"""외부 API 호출 공통 처리.

- 시간 초과 · 연결 오류 · 5xx → UPSTREAM_ERROR
- 401/403 → INVALID_KEY (공공데이터포털은 활용신청하지 않은 API 도 403·코드 30 으로 답함)
- 오류 원문은 키가 든 URL 을 포함할 수 있어 메시지에 넣지 않는다 (NF3002).
"""

from __future__ import annotations

from typing import Any

import requests

from backend.config import HTTP_TIMEOUT

from .base import Err


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get(url: str, *, params: dict | None = None, headers: dict | None = None, as_json: bool = True) -> Any:
    try:
        res = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:  # 메시지에 URL(키 포함)을 싣지 않는다
        raise ApiError(Err.UPSTREAM_ERROR, "외부 API에 연결하지 못했습니다.") from e
    if res.status_code in (401, 403):
        raise ApiError(Err.INVALID_KEY, "인증키가 없거나 해당 API 활용신청이 되어 있지 않습니다.")
    if res.status_code == 429:
        raise ApiError(Err.QUOTA_EXCEEDED, "외부 API 호출 한도를 넘었습니다.")
    if res.status_code >= 400:
        raise ApiError(Err.UPSTREAM_ERROR, f"외부 API가 오류를 돌려줬습니다 (HTTP {res.status_code}).")
    if not as_json:
        return res.content
    try:
        return res.json()
    except ValueError as e:
        # 공공데이터포털 게이트웨이 오류는 JSON 요청에도 XML 로 온다
        if b"SERVICE_KEY" in res.content or b"SERVICE ERROR" in res.content:
            raise ApiError(Err.INVALID_KEY, "인증키 오류 응답을 받았습니다.") from e
        raise ApiError(Err.UPSTREAM_ERROR, "외부 API 응답을 해석하지 못했습니다.") from e
