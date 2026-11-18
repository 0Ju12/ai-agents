"""search_tour · get_visit_info — 한국관광공사 국문 관광정보 서비스 (공공데이터포털 15101578).

TODO(1일차): 활용신청 후 실제 응답으로 확인할 것
- 서비스 경로(KorService2)와 기능명(locationBasedList2, detailIntro2)
- 소개정보의 운영시간·쉬는 날 필드명 (관광지 usetime·restdate, 음식점 opentimefood·restdatefood 로 알려져 있음)
"""

from __future__ import annotations

from backend.config import get_key

from .base import Err, fail, ok
from .http import ApiError, get

BASE = "https://apis.data.go.kr/B551011/KorService2"
CONTENT_TYPE = {"attraction": 12, "culture": 14, "festival": 15, "lodging": 32, "restaurant": 39}
COMMON = {"MobileOS": "ETC", "MobileApp": "TripPlanner", "_type": "json"}


def _items(body: dict) -> list[dict]:
    items = (((body.get("response") or {}).get("body") or {}).get("items")) or {}
    item = items.get("item", []) if isinstance(items, dict) else []
    return item if isinstance(item, list) else [item]


def search_tour(lat: float, lon: float, kind: str = "attraction", radius_m: int = 5000, limit: int = 20) -> dict:
    key = get_key("data_go_kr")
    if not key:
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    if kind not in CONTENT_TYPE:
        return fail(Err.BAD_ARGUMENT, f"kind 는 {list(CONTENT_TYPE)} 중 하나여야 합니다.")
    params = {**COMMON, "serviceKey": key, "mapX": lon, "mapY": lat, "radius": radius_m,
              "contentTypeId": CONTENT_TYPE[kind], "numOfRows": limit, "pageNo": 1, "arrange": "E"}
    try:
        items = _items(get(f"{BASE}/locationBasedList2", params=params))
    except ApiError as e:
        return fail(e.code, e.message)
    if not items:
        return fail(Err.NO_PLACE, "주변에서 후보를 찾지 못했습니다.")
    places = [{
        "kind": kind, "name": it.get("title", ""), "source": "tourapi", "source_id": str(it.get("contentid", "")),
        "lat": float(it["mapy"]) if it.get("mapy") else None, "lon": float(it["mapx"]) if it.get("mapx") else None,
        "address": it.get("addr1", ""), "distance_m": it.get("dist"),
    } for it in items]
    return ok({"places": places})


def get_visit_info(content_id: str, kind: str = "attraction") -> dict:
    """운영시간·쉬는 날 원문을 돌려준다. 해석(시각 추출)은 Agent 가 하고 근거 문장을 로그에 남긴다."""
    key = get_key("data_go_kr")
    if not key:
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    if not content_id:
        return fail(Err.BAD_ARGUMENT, "content_id 는 필수입니다.")
    params = {**COMMON, "serviceKey": key, "contentId": content_id, "contentTypeId": CONTENT_TYPE.get(kind, 12)}
    try:
        items = _items(get(f"{BASE}/detailIntro2", params=params))
    except ApiError as e:
        return fail(e.code, e.message)
    if not items:
        return fail(Err.NOT_FOUND, f"소개정보가 없습니다: {content_id}")
    it = items[0]
    # TODO(1일차): 실제 필드명 확인 후 정리. 비어 있으면 None 그대로 (임의로 채우지 않음)
    hours = it.get("usetime") or it.get("opentimefood") or it.get("usetimeculture") or None
    closed = it.get("restdate") or it.get("restdatefood") or it.get("restdateculture") or None
    fee = it.get("usefee") or None
    if not hours:
        return fail(Err.NO_HOURS, "운영시간 정보가 없어 판정을 보류합니다.")
    return ok({"content_id": content_id, "hours_text": hours, "closed_text": closed, "fee_text": fee,
               "menu": it.get("firstmenu") or None})
