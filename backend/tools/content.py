"""get_videos · make_insta_links — 장소별 참고 콘텐츠.

영상·게시물은 참고용이다. 운영시간 같은 판단 근거는 여기서 뽑지 않는다 (F3008).

YouTube Data API v3: 하루 기본 10,000 단위, search.list 1회 100 단위 → 하루 약 100회.
같은 검색어는 캐시에서 돌려준다 (TODO: SQLite 캐시로 교체해 재시작 후에도 유지).

Instagram: 3회차는 API 없이 해시태그 탐색 링크만 만든다. 스크래핑은 하지 않는다.
최종 프로젝트에서 Graph API(비즈니스 계정 · 7일 30개 해시태그 제한)로 교체.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from backend.config import get_key

from .base import Err, fail, ok
from .http import ApiError, get

YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_S = 24 * 3600


def get_videos(query: str, max_results: int = 3, within_days: int = 730) -> dict:
    if not query:
        return fail(Err.BAD_ARGUMENT, "query 는 필수입니다.")
    cache_key = f"{query}|{max_results}|{within_days}"
    hit = _CACHE.get(cache_key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return ok({**hit[1], "cached": True})
    key = get_key("youtube")
    if not key:
        return fail(Err.INVALID_KEY, "YouTube API 키(YOUTUBE_API_KEY)가 없습니다.")
    after = (datetime.now(timezone.utc) - timedelta(days=within_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"key": key, "part": "snippet", "q": query, "type": "video", "maxResults": min(max_results, 10),
              "publishedAfter": after, "relevanceLanguage": "ko", "regionCode": "KR"}
    try:
        body = get(YT_SEARCH, params=params)
    except ApiError as e:
        # 할당량 초과는 403 으로 오는 경우가 있어 INVALID_KEY 와 구분이 어려움 → 메시지로 안내
        return fail(e.code, e.message)
    videos = [{
        "video_id": it["id"]["videoId"], "title": it["snippet"]["title"], "channel": it["snippet"]["channelTitle"],
        "published_at": it["snippet"]["publishedAt"][:10], "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}",
    } for it in body.get("items", []) if it.get("id", {}).get("videoId")]
    if not videos:
        return fail(Err.NO_DATA, f"'{query}' 관련 최근 영상을 찾지 못했습니다.")
    data = {"query": query, "videos": videos}
    _CACHE[cache_key] = (time.time(), data)
    return ok({**data, "cached": False})


def _tag(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_]", "", text)


def make_insta_links(place_names: list[str], region: str = "") -> dict:
    """장소·지역 해시태그 탐색 링크 (API 불필요)."""
    if not place_names:
        return fail(Err.BAD_ARGUMENT, "place_names 는 하나 이상 필요합니다.")
    tags: list[str] = []
    for name in place_names:
        t = _tag(name)
        if t and t not in tags:
            tags.append(t)
    if region:
        for suffix in ("여행", "맛집", "카페"):
            t = _tag(region) + suffix
            if t not in tags:
                tags.append(t)
    links = [{"tag": f"#{t}", "url": f"https://www.instagram.com/explore/tags/{quote(t)}/"} for t in tags]
    return ok({"links": links, "note": "Instagram 해시태그 탐색 페이지 링크입니다 (게시물은 수집하지 않음)."})
