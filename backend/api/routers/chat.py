from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.agent import runner
from backend.config import key_status
from backend.store.db import Store

from ..deps import get_store
from ..schemas import ChatIn, ChatOut

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, _store: Store = Depends(get_store)):  # 저장소를 먼저 만들어 로깅 Agent 가 구독하게 함
    return runner.run(body.message, body.session_id)


@router.get("/status")
def status():
    """화면의 키 설정 안내용 — 키 값이 아니라 있는지만 (NF3002)."""
    return {"keys": key_status()}
