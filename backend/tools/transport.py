"""plan_leg — 이동 수단별 구간 안내 (어디서 무엇을 타고 몇 시에 도착하는지).

| mode     | 출처                                   | 주는 값 |
|----------|----------------------------------------|---------|
| train    | TAGO 열차정보 (15098552)                | 출발·도착역, 열차번호, 시각, 요금 |
| express  | TAGO 고속버스정보 (15098522)            | 출발·도착 터미널, 등급, 시각, 요금 |
| intercity| TAGO 시외버스정보 (15098541)            | 같음 |
| car      | 카카오모빌리티 길찾기                   | 거리, 소요시간 |
| transit  | ODsay 대중교통 (선택)                   | 정류장·노선·환승, 소요시간 |

잔여석은 어느 API 도 주지 않으므로 응답에 'seat_unknown': True 를 붙인다.
TODO(1일차): TAGO 기능명·응답 필드, 터미널·역 ID 조회 흐름 확인.
"""

from __future__ import annotations

from backend.config import get_key

from .base import Err, fail, ok
from .http import ApiError, get

KAKAO_DIRECTIONS = "https://apis-navi.kakaomobility.com/v1/directions"
MODES = {"train", "express", "intercity", "car", "transit"}


def _car(origin: dict, dest: dict) -> dict:
    key = get_key("kakao_rest")
    if not key:
        return fail(Err.INVALID_KEY, "카카오 REST 키(KAKAO_REST_API_KEY)가 없습니다.")
    params = {"origin": f"{origin['lon']},{origin['lat']}", "destination": f"{dest['lon']},{dest['lat']}"}
    try:
        body = get(KAKAO_DIRECTIONS, params=params, headers={"Authorization": f"KakaoAK {key}"})
    except ApiError as e:
        return fail(e.code, e.message)
    routes = body.get("routes") or []
    if not routes or routes[0].get("result_code") != 0:
        return fail(Err.NO_SERVICE, "자동차 경로를 찾지 못했습니다.")
    s = routes[0]["summary"]
    return ok({"mode": "car", "distance_km": round(s["distance"] / 1000, 1), "duration_min": round(s["duration"] / 60),
               "how": f"자가용 약 {round(s['duration'] / 60)}분 ({round(s['distance'] / 1000, 1)}km)",
               "map_url": f"https://map.kakao.com/link/to/{dest.get('name', '도착지')},{dest['lat']},{dest['lon']}"})


def plan_leg(mode: str, origin: dict, destination: dict, date: str = "", depart_after: str = "") -> dict:
    """origin/destination: {"name", "lat", "lon"} (도시 간 구간은 name 에 도시·역·터미널 이름)."""
    if mode not in MODES:
        return fail(Err.BAD_ARGUMENT, f"mode 는 {sorted(MODES)} 중 하나여야 합니다.")
    if not origin or not destination:
        return fail(Err.BAD_ARGUMENT, "origin 과 destination 은 필수입니다.")
    if mode == "car":
        if not all(k in d for d in (origin, destination) for k in ("lat", "lon")):
            return fail(Err.NO_COORD, "자가용 경로에는 출발지·도착지 좌표가 필요합니다.")
        return _car(origin, destination)
    if mode == "transit":
        if not get_key("odsay"):
            return fail(Err.INVALID_KEY, "ODsay 키가 없습니다. 카카오맵 길찾기 링크로 대신합니다.")
        return fail(Err.NOT_IMPLEMENTED, "ODsay 대중교통 경로는 1일차에 구현합니다.")
    # train / express / intercity — TAGO
    if not get_key("data_go_kr"):
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    return fail(Err.NOT_IMPLEMENTED, f"TAGO {mode} 시간표 조회는 1일차에 기능명 확인 후 구현합니다.")
