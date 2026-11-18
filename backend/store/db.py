"""SQLite 저장소 — 여행 계획(F3015~F3016)과 실행 로그(F3013~F3014).

실행 로그는 추가 · 조회 · 삭제만 있고 수정 함수는 없다 (F3014).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from backend.domain.constraints import intervals_overlap

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    trip_date   TEXT NOT NULL,        -- YYYY-MM-DD
    start_time  TEXT NOT NULL,        -- HH:MM
    end_time    TEXT NOT NULL,        -- HH:MM
    items_json  TEXT NOT NULL DEFAULT '[]',   -- 장소별 도착·출발, 구간별 교통편
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    type        TEXT NOT NULL,
    name        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_logs_session ON run_logs(session_id, seq);
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    # ── 계획 ──────────────────────────────────────────
    def create_plan(self, title: str, trip_date: str, start_time: str, end_time: str, items: list | None = None) -> tuple[dict, list[dict]]:
        """저장하고, 같은 날 시간이 겹치는 기존 계획을 함께 돌려준다 (저장을 막지 않음)."""
        overlaps = self.find_overlaps(trip_date, start_time, end_time)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO plans (title, trip_date, start_time, end_time, items_json, created_at) VALUES (?,?,?,?,?,?)",
                (title, trip_date, start_time, end_time, json.dumps(items or [], ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
        return self.get_plan(cur.lastrowid), overlaps

    def list_plans(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM plans ORDER BY trip_date, start_time").fetchall()
        return [self._plan(r) for r in rows]

    def get_plan(self, plan_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return self._plan(row) if row else None

    def update_plan(self, plan_id: int, **fields) -> dict | None:
        allowed = {"title", "trip_date", "start_time", "end_time", "items"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            if k == "items":
                k, v = "items_json", json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            vals.append(v)
        if sets:
            with self._lock:
                self._conn.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id=?", (*vals, plan_id))
                self._conn.commit()
        return self.get_plan(plan_id)

    def delete_plan(self, plan_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def find_overlaps(self, trip_date: str, start_time: str, end_time: str, exclude_id: int | None = None) -> list[dict]:
        s, e = _dt(trip_date, start_time), _dt(trip_date, end_time)
        rows = self._conn.execute("SELECT * FROM plans WHERE trip_date=?", (trip_date,)).fetchall()
        return [
            self._plan(r)
            for r in rows
            if r["id"] != exclude_id and intervals_overlap(s, e, _dt(r["trip_date"], r["start_time"]), _dt(r["trip_date"], r["end_time"]))
        ]

    @staticmethod
    def _plan(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["items"] = json.loads(d.pop("items_json"))
        return d

    # ── 실행 로그 (수정 함수 없음) ─────────────────────
    def append_log(self, session_id: str, seq: int, type_: str, name: str, payload: dict, ts: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO run_logs (session_id, seq, type, name, payload, ts) VALUES (?,?,?,?,?,?)",
                (session_id, seq, type_, name, json.dumps(payload, ensure_ascii=False, default=str), ts),
            )
            self._conn.commit()

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT session_id, COUNT(*) AS events, MIN(ts) AS started_at, MAX(ts) AS ended_at, "
            "SUM(type='replan') AS replans, SUM(type='tool_call') AS tool_calls "
            "FROM run_logs GROUP BY session_id ORDER BY started_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_logs(self, session_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM run_logs WHERE session_id=? ORDER BY seq", (session_id,)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def delete_session_logs(self, session_id: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM run_logs WHERE session_id=?", (session_id,))
            self._conn.commit()
        return cur.rowcount


def _dt(d: str, t: str) -> datetime:
    return datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
