"""FastAPI 앱 (F3017).

실행 (저장소 루트에서):
    uvicorn backend.api.main:app --reload
화면은 http://localhost:8000/ (frontend/ 를 정적 파일로 제공)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import chat, logs, plans

app = FastAPI(title="종합 여행 플래너 Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(chat.router)
app.include_router(plans.router)
app.include_router(logs.router)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
