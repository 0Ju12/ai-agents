"""get_holidays · get_weather · get_crowd — 공휴일, 날씨, 혼잡 예측.

- 특일: 천문연 특일정보 getRestDeInfo (15012690) — 명세 확인함
- 날씨: 기상청 단기예보(3일 이내) / 중기예보(3~10일) — 날짜에 따라 골라 부름
- 혼잡: 관광지 집중률 방문자 추이 예측 (15128555)
TODO(1일차): 기상청 격자 변환(위경도 → nx, ny), 중기예보 예보구역 코드, 집중률 응답 필드.
"""

from __future__ import annotations

from backend.config import get_key

from .base import Err, fail, ok
from .http import ApiError, get

HOLIDAY_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


def get_holidays(year: int, month: int) -> dict:
    key = get_key("data_go_kr")
    if not key:
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    if not (1 <= int(month) <= 12):
        return fail(Err.BAD_ARGUMENT, "month 는 1~12 입니다.")
    params = {"ServiceKey": key, "solYear": int(year), "solMonth": f"{int(month):02d}", "_type": "json", "numOfRows": 50}
    try:
        body = get(HOLIDAY_URL, params=params)
    except ApiError as e:
        return fail(e.code, e.message)
    items = (((body.get("response") or {}).get("body") or {}).get("items")) or {}
    item = items.get("item", []) if isinstance(items, dict) else []
    item = item if isinstance(item, list) else [item]
    days = [{"date": f"{str(i['locdate'])[:4]}-{str(i['locdate'])[4:6]}-{str(i['locdate'])[6:]}", "name": i.get("dateName", "")}
            for i in item if i.get("isHoliday") == "Y"]
    return ok({"holidays": days})  # 공휴일이 없는 달은 빈 목록 (실패 아님)


def get_weather(lat: float, lon: float, date: str) -> dict:
    if not get_key("data_go_kr"):
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    return fail(Err.NOT_IMPLEMENTED, "단기·중기예보 선택 호출은 1일차에 구현합니다.")


def get_crowd(area_code: str, date: str) -> dict:
    if not get_key("data_go_kr"):
        return fail(Err.INVALID_KEY, "공공데이터포털 인증키(DATA_GO_KR_SERVICE_KEY)가 없습니다.")
    return fail(Err.NOT_IMPLEMENTED, "관광지 집중률 예측은 1일차에 구현합니다.")
