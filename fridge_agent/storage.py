"""Versioned kitchen state. Read outside the write transaction, commit with revision + receipt."""

from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.store.db import Store
from domain.catalog import load_catalog

household = ContextVar("household", default="local")
KST = ZoneInfo("Asia/Seoul")


def today():
    return datetime.now(KST).date()


def root():
    path = Path(os.getenv("FRIDGE_DATA_DIR", ".")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def home_dir():
    path = root() if household.get() == "local" else root() / "homes" / household.get()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


@lru_cache(maxsize=128)
def history(path):
    return Store(path)


def local_store():
    return history(str(home_dir() / "fridge_history.sqlite3"))


@lru_cache(maxsize=16)
def catalog_at(path):
    return load_catalog(path)


def catalog():
    return catalog_at(str(root() / "food_catalog.sqlite3"))


class RevisionConflict(Exception):
    pass


class ReceiptConflict(Exception):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS kitchens(session TEXT PRIMARY KEY, revision INTEGER NOT NULL, settings TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lots(session TEXT, id TEXT, item TEXT NOT NULL, grams REAL, expires TEXT, PRIMARY KEY(session,id));
CREATE TABLE IF NOT EXISTS batches(session TEXT, id TEXT, title TEXT NOT NULL, servings INTEGER, facts TEXT, PRIMARY KEY(session,id));
CREATE TABLE IF NOT EXISTS days(session TEXT, day TEXT, body TEXT, PRIMARY KEY(session,day));
CREATE TABLE IF NOT EXISTS receipts(session TEXT, id TEXT, fingerprint TEXT NOT NULL, reply TEXT NOT NULL, PRIMARY KEY(session,id));
"""


def new_state():
    return {
        "minutes": 30,
        "goal": "체력",
        "lots": [],
        "batches": [],
        "daily": {},
        "records": [],
        "workouts": [],
    }


class KitchenDB:
    def __init__(self, path=None):
        self.path = Path(path) if path else home_dir() / "fridge.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def read(self, session):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM kitchens WHERE session=?", (session,)).fetchone()
            if row is None:
                state = new_state()
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone():
                    scoped = any(r["name"] == "session" for r in db.execute("PRAGMA table_info(runs)"))
                    if scoped or session == "default":
                        sql = (
                            "SELECT state FROM runs"
                            + (" WHERE session=?" if scoped else "")
                            + " ORDER BY id DESC LIMIT 1"
                        )
                        old = db.execute(sql, (session,) if scoped else ()).fetchone()
                        if old:
                            legacy = json.loads(old[0])
                            state.update(legacy)
                            if legacy.get("substitute"):
                                state["swaps"] = {"대파": "양파"}
                            state["lots"] = [
                                {"id": uuid4().hex, "item": x, "grams": None, "expires": None}
                                for x in state.pop("stock", [])
                            ]
                            state["batches"] = [
                                {"id": uuid4().hex, "title": k, "servings": v, "facts": {}}
                                for k, v in state.pop("leftovers", {}).items()
                                if v
                            ]
                return 0, state
            state = json.loads(row["settings"])
            state["lots"] = [
                dict(r)
                for r in db.execute(
                    "SELECT id,item,grams,expires FROM lots WHERE session=? ORDER BY rowid", (session,)
                )
            ]
            state["batches"] = [
                {**dict(r), "facts": json.loads(r["facts"])}
                for r in db.execute(
                    "SELECT id,title,servings,facts FROM batches WHERE session=? ORDER BY rowid", (session,)
                )
            ]
            state["daily"] = {
                r["day"]: json.loads(r["body"])
                for r in db.execute("SELECT day,body FROM days WHERE session=?", (session,))
            }
            return row["revision"], state

    @staticmethod
    def replay(db, session, req_id, fingerprint):
        if req_id:
            r = db.execute(
                "SELECT fingerprint,reply FROM receipts WHERE session=? AND id=?", (session, req_id)
            ).fetchone()
            if r:
                if r["fingerprint"] != fingerprint:
                    raise ReceiptConflict()
                return json.loads(r["reply"])

    def receipt(self, session, key, fingerprint):
        with self.connect() as db:
            return self.replay(db, session, key, fingerprint)

    def commit(self, session, revision, state, reply, key, fingerprint):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self.replay(db, session, key, fingerprint)
            if previous is not None:
                return previous
            row = db.execute("SELECT revision FROM kitchens WHERE session=?", (session,)).fetchone()
            if (row[0] if row else 0) != revision:
                raise RevisionConflict()
            settings = {k: v for k, v in state.items() if k not in {"lots", "batches", "daily"}}
            db.execute(
                "INSERT OR REPLACE INTO kitchens VALUES(?,?,?)", (session, revision + 1, compact(settings))
            )
            for table in ("lots", "batches"):
                db.execute(f"DELETE FROM {table} WHERE session=?", (session,))
            db.executemany(
                "INSERT INTO lots VALUES(?,?,?,?,?)",
                [(session, x["id"], x["item"], x["grams"], x["expires"]) for x in state["lots"]],
            )
            db.executemany(
                "INSERT INTO batches VALUES(?,?,?,?,?)",
                [
                    (session, x["id"], x["title"], x["servings"], compact(x["facts"]))
                    for x in state["batches"]
                ],
            )
            db.executemany(
                "INSERT OR REPLACE INTO days VALUES(?,?,?)",
                [(session, k, compact(v)) for k, v in state["daily"].items()],
            )
            if key:
                db.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?)", (session, key, fingerprint, compact(reply))
                )
        return reply


def fingerprint(message, params):
    return hashlib.sha256(compact([message, params]).encode()).hexdigest()
