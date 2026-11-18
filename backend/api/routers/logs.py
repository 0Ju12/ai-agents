"""실행 로그 API — 목록 · 상세 · 삭제만 둔다. 수정 API 는 만들지 않는다 (F3014).
기록을 고칠 수 있으면 관찰의 의미가 사라지기 때문이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.store.db import Store

from ..deps import get_store

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_sessions(store: Store = Depends(get_store)):
    return store.list_sessions()


@router.get("/{session_id}")
def get_session(session_id: str, store: Store = Depends(get_store)):
    logs = store.get_session_logs(session_id)
    if not logs:
        raise HTTPException(404, "그 세션의 실행 로그가 없습니다.")
    return logs


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, store: Store = Depends(get_store)):
    if store.delete_session_logs(session_id) == 0:
        raise HTTPException(404, "그 세션의 실행 로그가 없습니다.")
