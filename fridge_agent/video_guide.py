"""조리 모드의 영상 탭: YouTube 챕터를 조리 단계에 맞추고, Instagram 게시물을 공식 임베드로 보여 준다.

- YouTube: search(100단위) 1회 + videos.list(1단위) 1회, 메뉴별 결과를 24시간 캐시한다.
  설명란의 '02:15 양파 볶기' 같은 챕터 줄을 읽고, 단계마다 시작 초를 정한다.
  단계-챕터 짝은 규칙(단어 겹침)으로 먼저 정하고, 모델이 있으면 보충한다. 모델 결과는
  챕터 범위 안 · 단계 순서대로(시간이 거꾸로 가지 않게)인 것만 받는다.
- 자막은 영상 소유자만 받을 수 있어 쓰지 않는다.
- Instagram: Graph API 해시태그 결과(키·앱 검수 필요)의 permalink 를 화면에서 embed.js 로 임베드한다.
"""

import json
import os
import re
import sqlite3
import time
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

from cook_guide import detect_action
from menu_match import ingredient_names
from connections import fail, instagram, need
from gateway import request_json

CHAPTER = re.compile(r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-–—:|]?\s*(.+?)\s*$")
TTL = 86400


def seconds(stamp):
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def parse_chapters(description):
    """설명란에서 챕터 목록. 0초에서 시작하고 시간이 늘어나는 3개 이상일 때만 챕터로 본다(YouTube 규칙과 같다)."""
    found = []
    for line in (description or "").splitlines():
        m = CHAPTER.match(line)
        if m and len(m[2]) <= 80:
            found.append({"start": seconds(m[1]), "title": unescape(m[2])})
    ok = len(found) >= 3 and found[0]["start"] == 0 and all(a["start"] < b["start"] for a, b in zip(found, found[1:]))
    return found if ok else []


def words(text):
    """한국어는 조사·어미가 붙어 단어가 달라지므로 두 글자 조각으로 비교한다 (두부를 ↔ 두부)."""
    out = set()
    for w in re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text or ""):
        out.update(w[i : i + 2] for i in range(len(w) - 1)) if re.match("[가-힣]", w) else out.add(w.lower())
    return out


def match_rule(steps, chapters):
    """단계마다 단어가 가장 많이 겹치는 챕터. 앞 단계보다 이른 챕터는 고르지 않는다."""
    starts, floor = [], 0
    subjects = (*ingredient_names(), "삼겹살", "닭고기")
    for text in steps:
        action = detect_action(text)
        ingredients = {name for name in subjects if name in text}
        best, score = None, 0
        for i in range(floor, len(chapters)):
            title = chapters[i]["title"]
            if action == "준비" or action != detect_action(title):
                continue
            chapter_ingredients = {name for name in subjects if name in title}
            if ingredients and chapter_ingredients and not ingredients.intersection(chapter_ingredients):
                continue
            s = len(words(text) & words(title))
            if s > score:
                best, score = i, s
        if best is not None:
            floor = best
        starts.append(chapters[best]["start"] if best is not None else None)
    return starts


def cache(name, build):
    path = Path(os.getenv("FRIDGE_DATA_DIR", ".")) / "food_catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS media_cache(name TEXT PRIMARY KEY, fetched REAL, result TEXT)")
        row = db.execute("SELECT fetched,result FROM media_cache WHERE name=?", (name,)).fetchone()
        if row and time.time() - row[0] < TTL:
            return json.loads(row[1])
        result = build()
        if result.get("ok"):
            db.execute("INSERT OR REPLACE INTO media_cache VALUES(?,?,?)", (name, time.time(), json.dumps(result, ensure_ascii=False)))
        return result


def youtube_videos(menu, kind="recipe"):
    """임베드 가능한 조리 영상과 설명란 챕터. 키가 없으면 MISSING_KEY."""
    absent = need("YOUTUBE_API_KEY")
    if absent:
        return absent

    def build():
        base, key = "https://www.googleapis.com/youtube/v3/", os.environ["YOUTUBE_API_KEY"]
        found = request_json(
            base + "search?" + urlencode({
                "part": "snippet", "q": menu + (" 운동 자세" if kind == "workout" else " 레시피 만들기"), "type": "video", "videoEmbeddable": "true",
                "regionCode": "KR", "relevanceLanguage": "ko", "maxResults": 5, "key": key,
            })
        )
        ids = [x["id"]["videoId"] for x in found.get("items", []) if x.get("id", {}).get("videoId")]
        if not ids:
            return fail("NO_RESULT")
        details = request_json(base + "videos?" + urlencode({"part": "snippet,statistics", "id": ",".join(ids), "key": key}))
        videos = [
            {
                "id": x["id"],
                "title": unescape(x["snippet"]["title"]),
                "channel": x["snippet"]["channelTitle"],
                "views": int(x.get("statistics", {}).get("viewCount", 0) or 0),
                "url": "https://www.youtube.com/watch?v=" + x["id"],
                "chapters": parse_chapters(x["snippet"].get("description")),
            }
            for x in details.get("items", [])
            if re.fullmatch(r"[\w-]{11}", x.get("id", ""))
        ]
        # 챕터가 있는 영상 우선, 그다음 조회수
        videos.sort(key=lambda v: (not v["chapters"], -v["views"]))
        return {"ok": True, "data": videos, "source": "YouTube Data API · 임베드 가능한 영상, 설명란 챕터"}

    return cache(f"youtube:{kind}:" + menu, build)


def media_for(menu, steps, emit, kind="recipe"):
    from urllib.error import HTTPError

    emit("tool_call", "youtube", argument=menu)
    try:
        yt = youtube_videos(menu, kind)
    except (HTTPError, OSError, ValueError, KeyError):
        yt = fail("SOURCE_UNAVAILABLE")
    if yt.get("ok"):
        key = re.sub(r"[^\w]", "", menu).casefold()
        videos = []
        for row in yt["data"]:
            if not key or key not in re.sub(r"[^\w]", "", row["title"]).casefold():
                continue
            chapters = row["chapters"]
            videos.append({
                **row,
                "step_starts": match_rule(steps, chapters),
                "matching": "규칙" if chapters else "챕터 없음",
            })
        yt = {**yt, "data": videos} if videos else fail("NO_RESULT")
    emit("tool_result", "youtube", ok=yt.get("ok", False), error=yt.get("error"))
    emit("tool_call", "instagram", argument=menu)
    try:
        ig = instagram(menu.replace(" ", ""))
    except (HTTPError, OSError, ValueError, KeyError):
        ig = fail("SOURCE_UNAVAILABLE")
    emit("tool_result", "instagram", ok=ig.get("ok", False), error=ig.get("error"))
    if ig.get("ok"):
        ig["data"] = [x for x in ig["data"] if re.match(r"^https://www\.instagram\.com/(p|reel)/[\w-]+/?", x.get("url", ""))]
    tag = re.sub(r"[^\w]", "", menu)
    return {
        "youtube": yt,
        "instagram": ig,
        "직접 검색": {
            "YouTube": "https://www.youtube.com/results?search_query=" + urlencode({"q": menu + (" 운동 자세" if kind == "workout" else " 레시피")})[2:],
            "Instagram": "https://www.instagram.com/explore/tags/" + urlencode({"q": tag})[2:] + "/",
        },
    }
