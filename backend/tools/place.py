"""search_place — 카카오 로컬 카테고리 검색 (카페·음식점 보충).

TourAPI 에 카페가 적어 카카오로 보충한다. 카카오는 영업시간·평점을 주지 않으므로
카페의 운영시간은 None(→ '영업시간 미확인' 표시)으로 둔다.
"""

from __future__ import annotations

from backend.config import get_key

from .base import Err, fail, ok
from .http import ApiError, get

URL = "https://dapi.kakao.com/v2/local/search/category.json"
CATEGORY = {"cafe": "CE7", "restaurant": "FD6", "attraction": "AT4", "culture": "CT1"}


def search_place(lat: float, lon: float, kind: str = "cafe", radius_m: int = 1000, limit: int = 15) -> dict:
    key = get_key("kakao_rest")
    if not key:
        return fail(Err.INVALID_KEY, "카카오 REST 키(KAKAO_REST_API_KEY)가 없습니다.")
    if kind not in CATEGORY:
        return fail(Err.BAD_ARGUMENT, f"kind 는 {list(CATEGORY)} 중 하나여야 합니다.")
    params = {"category_group_code": CATEGORY[kind], "x": lon, "y": lat, "radius": min(radius_m, 20000),
              "sort": "distance", "size": min(limit, 15)}
    try:
        body = get(URL, params=params, headers={"Authorization": f"KakaoAK {key}"})
    except ApiError as e:
        return fail(e.code, e.message)
    docs = body.get("documents", [])
    if not docs:
        return fail(Err.NO_PLACE, f"반경 {radius_m}m 안에서 {kind} 후보를 찾지 못했습니다.")
    places = [{
        "kind": kind, "name": d.get("place_name", ""), "source": "kakao", "source_id": d.get("id", ""),
        "lat": float(d["y"]), "lon": float(d["x"]), "address": d.get("road_address_name") or d.get("address_name", ""),
        "distance_m": int(d["distance"]) if d.get("distance") else None, "url": d.get("place_url", ""),
        "hours_text": "",  # 카카오 API 는 영업시간을 주지 않음
    } for d in docs]
    return ok({"places": places})
