"""Single contract for a local calendar and an explicitly authorized Google calendar."""

from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from storage import home_dir, household, local_store, KST
from gateway import request_json


def token_file():
    return home_dir() / "google-calendar.json"


def google_call(path, args=None, body=None, method=None):
    file = token_file()
    if not file.is_file():
        return {"ok": False, "error": "CALENDAR_NOT_CONNECTED"}
    cred = json.loads(file.read_text())
    auth = urlencode(
        {
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "refresh_token": cred["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    with urlopen(Request("https://oauth2.googleapis.com/token", data=auth), timeout=5) as response:
        access = json.load(response)["access_token"]
    base = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        + quote(cred.get("calendar_id", "primary"), safe="")
        + "/events"
    )
    return request_json(
        base + path + ("?" + urlencode(args) if args else ""),
        body,
        {"Authorization": "Bearer " + access},
        method=method,
    )


def calendar(operation, argument, provider=None):
    provider = provider or ("google" if token_file().is_file() else "local")
    try:
        if operation == "calendar_list":
            day = date.fromisoformat(argument)
            if provider == "local":
                with local_db() as db:
                    data = [
                        dict(zip(("id", "title", "start", "end"), r))
                        for r in db.execute(
                            "SELECT id,title,start,end FROM events WHERE day=? ORDER BY start", (argument,)
                        )
                    ]
            else:
                midnight = datetime.combine(day, datetime.min.time(), KST)
                args = {
                    "timeMin": midnight.isoformat(),
                    "timeMax": (midnight + timedelta(days=1)).isoformat(),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 2500,
                }
                data = []
                while True:
                    page = google_call("", args)
                    if page.get("ok") is False:
                        return page
                    for r in page.get("items", []):
                        if r.get("status") == "cancelled" or r.get("transparency") == "transparent":
                            continue

                        def hm(point, default):
                            if not point.get("dateTime"):
                                return default
                            dt = datetime.fromisoformat(
                                point["dateTime"].replace("Z", "+00:00")
                            ).astimezone(KST)
                            if dt.date() < day:
                                return "00:00"
                            if dt.date() > day:
                                return "24:00"
                            return dt.strftime("%H:%M")

                        data.append(
                            {
                                "id": r["id"],
                                "title": r.get("summary", "일정"),
                                "start": hm(r["start"], "00:00"),
                                "end": hm(r["end"], "24:00"),
                            }
                        )
                    if not page.get("nextPageToken"):
                        break
                    args["pageToken"] = page["nextPageToken"]
            return {"ok": True, "data": data, "source": provider}
        plan = local_store().get_plan(int(argument))
        if not plan:
            return {"ok": False, "error": "NO_RESULT"}
        day = plan["trip_date"]
        start, end = plan["start_time"], plan["end_time"]
        stable = hashlib.sha256(
            (household.get() + "/" + str(plan["id"]) + "/" + plan["created_at"]).encode()
        ).hexdigest()[:40]
        if provider == "local":
            with local_db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO events VALUES(?,?,?,?,?)",
                    (stable, day, plan["title"], start, end),
                )
        else:
            body = {
                "id": stable,
                "summary": plan["title"],
                "start": {"dateTime": day + "T" + start + ":00+09:00"},
                "end": {"dateTime": day + "T" + end + ":00+09:00"},
            }
            try:
                r = google_call("", body=body)
            except HTTPError as err:
                if err.code != 409:
                    raise
                r = google_call("/" + stable, body=body, method="PUT")
            if r.get("ok") is False:
                return r
        return {
            "ok": True,
            "data": {"id": stable, "title": plan["title"], "start": start, "end": end, "day": day},
            "source": provider,
        }
    except (ValueError, TypeError):
        return {"ok": False, "error": "INVALID_INPUT"}
    except (OSError, KeyError, sqlite3.Error):
        return {"ok": False, "error": "SOURCE_UNAVAILABLE"}


def local_db():
    db = sqlite3.connect(home_dir() / "calendar.sqlite3")
    db.execute(
        "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,day TEXT,title TEXT,start TEXT,end TEXT)"
    )
    return db


def earliest_window(start, minutes, events):
    def number(hm):
        h, m = map(int, hm.split(":"))
        return h * 60 + m

    first = number(start)
    end = min(1440, first + minutes)
    for e in events:
        a, b = number(e["start"]), number(e["end"])
        if b > first and a < end:
            end = max(first, a)
    return end - first
