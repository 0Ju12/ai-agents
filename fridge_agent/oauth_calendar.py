"""Google Calendar web OAuth. Single-use state and PKCE are scoped to the device."""

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from calendar_adapter import token_file
from storage import home_dir

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
SCOPES = "https://www.googleapis.com/auth/calendar.events"


def config():
    keys = [os.getenv(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")]
    if not all(keys):
        raise HTTPException(503, "Google Calendar OAuth 환경 설정이 필요합니다.")
    return keys


@router.get("/status")
def status():
    return {
        "provider": "google" if token_file().is_file() else "local",
        "oauth_available": all(
            os.getenv(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
        ),
    }


@router.get("/connect")
def connect():
    client, _, redirect = config()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with sqlite3.connect(home_dir() / "calendar.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS oauth(state TEXT PRIMARY KEY,verifier TEXT,expires REAL)")
        db.execute("DELETE FROM oauth WHERE expires<?", (time.time(),))
        db.execute("INSERT INTO oauth VALUES(?,?,?)", (state, verifier, time.time() + 600))
    args = {
        "client_id": client,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(args))


@router.get("/callback")
def callback(state: str, code: str = ""):
    client, secret, redirect = config()
    with sqlite3.connect(home_dir() / "calendar.sqlite3") as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS oauth(state TEXT PRIMARY KEY,verifier TEXT,expires REAL)")
        row = db.execute(
            "SELECT verifier FROM oauth WHERE state=? AND expires>=?", (state, time.time())
        ).fetchone()
        db.execute("DELETE FROM oauth WHERE state=?", (state,))
    if not row or not code:
        raise HTTPException(400, "연결 요청이 만료되었거나 취소됐습니다.")
    fields = {
        "client_id": client,
        "client_secret": secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
        "code_verifier": row[0],
    }
    try:
        with urlopen(
            Request("https://oauth2.googleapis.com/token", data=urlencode(fields).encode()), timeout=7
        ) as res:
            token = json.load(res)["refresh_token"]
    except (OSError, ValueError, KeyError):
        raise HTTPException(502, "Google 캘린더 승인을 확인하세요.") from None
    temp = token_file().with_suffix("." + secrets.token_hex(8) + ".tmp")
    with os.fdopen(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="utf-8") as f:
        json.dump({"client_id": client, "client_secret": secret, "refresh_token": token}, f)
    os.replace(temp, token_file())
    return RedirectResponse("/#journal", status_code=303)


@router.delete("/connection", status_code=204)
def disconnect():
    token_file().unlink(missing_ok=True)
