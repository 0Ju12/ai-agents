"""ask_heritage — 2회차 국보 RAG(heritage-rag-guide)를 Tool 로 감싼다 (F3022).

2회차 저장소의 ChromaDB 색인과 인용 번호 검증을 그대로 쓴다.
HERITAGE_RAG_DIR 가 비었거나 색인이 없으면 NO_INDEX 로 '아직 모으지 못했다'고 답한다.
TODO(2일차): heritage-rag-guide 의 services/assistant.py 진입점을 import 해 연결.
"""

from __future__ import annotations

from pathlib import Path

from backend.config import HERITAGE_RAG_DIR

from .base import Err, fail


def ask_heritage(question: str) -> dict:
    if not question:
        return fail(Err.BAD_ARGUMENT, "question 은 필수입니다.")
    if not HERITAGE_RAG_DIR or not (Path(HERITAGE_RAG_DIR) / "data" / "chroma").exists():
        return fail(Err.NO_INDEX, "국가유산 해설 색인이 아직 없습니다 (2회차 색인 경로 HERITAGE_RAG_DIR 확인).")
    return fail(Err.NOT_IMPLEMENTED, "2회차 RAG 연결은 2일차에 구현합니다.")
