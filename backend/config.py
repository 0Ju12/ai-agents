"""공통 계층 설정 — 키는 환경변수(.env)에서만 읽는다 (NF3001). 이 모듈은 저장 위치만 정한다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("PLANNER_DB", str(ROOT / "data" / "planner.db")))
