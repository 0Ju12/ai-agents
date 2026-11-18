"""설정과 API 키 — 키는 환경변수(.env)에서만 읽는다 (NF3001).

코드 어디에도 키 값을 적지 않는다. 키가 없으면 None을 돌려주고,
각 Tool은 이를 INVALID_KEY 실패로 바꿔 서비스가 멈추지 않게 한다 (NF3003).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 키 이름표 → 환경변수 이름
KEY_ENV = {
    "data_go_kr": "DATA_GO_KR_SERVICE_KEY",  # 공공데이터포털 (TourAPI, TAGO, 기상청, 특일, 집중률)
    "kakao_rest": "KAKAO_REST_API_KEY",  # 카카오 로컬 · 모빌리티
    "youtube": "YOUTUBE_API_KEY",  # YouTube Data API v3
    "odsay": "ODSAY_API_KEY",  # ODsay 대중교통 (선택)
    "openai": "OPENAI_API_KEY",  # LLM
}


def get_key(name: str) -> str | None:
    """키가 비어 있으면 None. 값은 로그·화면에 절대 내보내지 않는다."""
    value = os.getenv(KEY_ENV[name], "").strip()
    return value or None


def key_status() -> dict[str, bool]:
    """화면의 '키 설정 안내'용 — 값이 아니라 있는지만 알려 준다 (NF3002)."""
    return {name: get_key(name) is not None for name in KEY_ENV}


MAX_REPLAN = int(os.getenv("MAX_REPLAN", "3"))  # 재계획 상한 (F3009, NF3004)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = Path(os.getenv("PLANNER_DB", str(ROOT / "data" / "planner.db")))
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# 2회차 국보 RAG 저장소 경로 (F3022). 비어 있으면 ask_heritage 는 NO_INDEX
HERITAGE_RAG_DIR = os.getenv("HERITAGE_RAG_DIR", "")
