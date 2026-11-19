"""Domain connectors return evidence, origin, and a typed error. Credentials never enter responses."""

from datetime import datetime, timedelta, timezone
from html import unescape
import hashlib
import hmac
import os
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from gateway import request_json


def fail(code, **fields):
    return {"ok": False, "error": code, **fields}


def rows(items, source):
    return {"ok": True, "data": items, "source": source} if items else fail("NO_RESULT", source=source)


def need(*names):
    return next((fail("MISSING_KEY", setting=name) for name in names if not os.getenv(name)), None)


def naver(term):
    absent = need("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")
    if absent:
        return absent
    url = "https://openapi.naver.com/v1/search/shop.json?" + urlencode(
        {"query": term, "display": 6, "sort": "sim"}
    )
    data = request_json(
        url,
        headers={
            "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
        },
    )
    return rows(
        [
            {
                "id": x["productId"],
                "title": unescape(re.sub(r"<[^>]*>", "", x["title"])),
                "price_krw": int(x["lprice"]),
                "merchant": x.get("mallName"),
                "url": x["link"],
            }
            for x in data.get("items", [])
            if x.get("lprice", "").isdigit()
        ],
        "네이버 쇼핑",
    )


def coupang(term):
    absent = need("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY")
    if absent:
        return absent
    path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query = urlencode({"keyword": term, "limit": 5})
    stamp = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    sig = hmac.new(
        os.environ["COUPANG_SECRET_KEY"].encode(), (stamp + "GET" + path + query).encode(), hashlib.sha256
    ).hexdigest()
    auth = (
        "CEA algorithm=HmacSHA256, access-key="
        + os.environ["COUPANG_ACCESS_KEY"]
        + ", signed-date="
        + stamp
        + ", signature="
        + sig
    )
    data = request_json(
        "https://api-gateway.coupang.com" + path + "?" + query, headers={"Authorization": auth}
    )
    if data.get("rCode") != "0" and str(data.get("rCode")) != "0":
        return fail("PROVIDER_ERROR")
    return rows(
        [
            {
                "id": x["productId"],
                "title": x["productName"],
                "price_krw": x["productPrice"],
                "url": x["productUrl"],
                "merchant": "쿠팡",
            }
            for x in (data.get("data") or {}).get("productData", [])
        ],
        "쿠팡 파트너스 · 구매 시 수수료가 발생할 수 있습니다.",
    )


def youtube(term):
    absent = need("YOUTUBE_API_KEY")
    if absent:
        return absent
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    base = "https://www.googleapis.com/youtube/v3/"
    args = {
        "part": "snippet",
        "q": term + " 레시피",
        "type": "video",
        "publishedAfter": since.isoformat(),
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "order": "viewCount",
        "maxResults": 10,
        "key": os.environ["YOUTUBE_API_KEY"],
    }
    search = request_json(base + "search?" + urlencode(args))
    ids = [x["id"]["videoId"] for x in search.get("items", []) if x["id"].get("videoId")]
    if not ids:
        return fail("NO_RESULT")
    details = request_json(
        base
        + "videos?"
        + urlencode({"part": "snippet,statistics", "id": ",".join(ids), "key": args["key"]})
    )
    found = []
    for x in details.get("items", []):
        sn = x["snippet"]
        views = x.get("statistics", {}).get("viewCount")
        if views is None:
            continue
        when = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        if not since <= when <= now:
            continue
        pace = round(int(views) / max(1, (now - when).total_seconds() / 86400))
        found.append(
            {
                "title": unescape(sn["title"]),
                "channel": sn["channelTitle"],
                "published": when.date().isoformat(),
                "views": int(views),
                "views_per_day": pace,
                "url": "https://www.youtube.com/watch?v=" + x["id"],
            }
        )
    return rows(
        sorted(found, key=lambda x: -x["views_per_day"])[:5],
        "YouTube Data API · 최근 30일 검색 표본의 일평균 조회수",
    )


def instagram(term):
    absent = need("IG_USER_ID", "IG_ACCESS_TOKEN")
    if absent:
        return absent
    base = "https://graph.facebook.com/" + os.getenv("META_GRAPH_VERSION", "v25.0") + "/"
    auth = {"Authorization": "Bearer " + os.environ["IG_ACCESS_TOKEN"]}
    user = os.environ["IG_USER_ID"]
    tags = request_json(
        base + "ig_hashtag_search?" + urlencode({"user_id": user, "q": re.sub(r"[^\w]", "", term)}),
        headers=auth,
    ).get("data", [])
    if not tags:
        return fail("NO_RESULT")
    query = urlencode(
        {"user_id": user, "fields": "caption,permalink,timestamp,like_count,comments_count", "limit": 15}
    )
    data = request_json(base + str(tags[0]["id"]) + "/recent_media?" + query, headers=auth)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    records = [
        {
            "title": (x.get("caption") or term)[:90],
            "published": x["timestamp"][:10],
            "url": x["permalink"],
            "likes": x.get("like_count"),
            "comments": x.get("comments_count"),
        }
        for x in data.get("data", [])
        if x.get("permalink")
        and x.get("timestamp")
        and datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")) >= since
    ]
    return rows(
        sorted(
            records,
            key=lambda x: (x["likes"] is not None, (x["likes"] or 0) + (x["comments"] or 0)),
            reverse=True,
        )[:5],
        "Instagram Graph API · 조회 가능한 최근 게시물, 공개 반응 수 기준",
    )


def gyms(term):
    absent = need("KAKAO_REST_API_KEY")
    if absent:
        return absent
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?" + urlencode(
        {"query": term + " 헬스장", "size": 7}
    )
    data = request_json(url, headers={"Authorization": "KakaoAK " + os.environ["KAKAO_REST_API_KEY"]})
    return rows(
        [
            {
                "id": x["id"],
                "title": x["place_name"],
                "address": x.get("road_address_name") or x.get("address_name"),
                "url": x["place_url"],
            }
            for x in data.get("documents", [])
        ],
        "카카오 로컬",
    )


def usda(term):
    data = request_json(
        "https://api.nal.usda.gov/fdc/v1/foods/search?"
        + urlencode(
            {
                "query": term,
                "pageSize": 5,
                "dataType": "SR Legacy",
                "api_key": (os.getenv("USDA_API_KEY") or "DEMO_KEY"),
            }
        )
    )
    return rows(
        [
            {
                "id": x["fdcId"],
                "title": x["description"],
                "url": "https://fdc.nal.usda.gov/food-details/" + str(x["fdcId"]),
                "nutrients_per_100g": {
                    n["nutrientName"]: {"value": n.get("value"), "unit": n.get("unitName")}
                    for n in x.get("foodNutrients", [])
                    if n["nutrientId"] in (1003, 1004, 1005, 1008, 1079, 1093)
                },
            }
            for x in data.get("foods", [])
        ],
        "USDA FoodData Central · SR Legacy",
    )


EXTERNAL = {
    "naver": naver,
    "coupang": coupang,
    "youtube": youtube,
    "instagram": instagram,
    "gyms": gyms,
    "usda": usda,
}


def lookup(tool, term):
    if not term.strip() or len(term) > 120:
        return fail("INVALID_INPUT")
    try:
        return EXTERNAL[tool](term)
    except HTTPError as error:
        code = {
            400: "INVALID_INPUT",
            401: "AUTH_FAILED",
            403: "AUTH_FAILED",
            404: "NO_RESULT",
            429: "RATE_LIMIT",
        }.get(error.code, "SOURCE_UNAVAILABLE")
        return fail(code)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return fail("SOURCE_UNAVAILABLE")
