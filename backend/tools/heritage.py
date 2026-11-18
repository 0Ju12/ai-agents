"""search_heritage — 국가유산청 국가유산 검색 API (키 불필요, XML).

2회차 heritage-rag-guide 의 data_prep/khs_api.py 와 같은 엔드포인트를 쓴다.
응답 태그가 바뀌어도 깨지지 않도록 <item> 하위 태그를 전부 dict 로 받은 뒤 필요한 값만 뽑는다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from backend.domain.place import Place

from .base import Err, fail, ok
from .http import ApiError, get

LIST_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiList.do"
KIND = {"국보": "11", "보물": "12", "사적": "13"}
# 시도 코드 (국가유산청 ccbaCtcd)
SIDO = {
    "서울": "11", "부산": "21", "대구": "22", "인천": "23", "광주": "24", "대전": "25", "울산": "26", "세종": "45",
    "경기": "31", "강원": "32", "충북": "33", "충남": "34", "전북": "35", "전남": "36", "경북": "37", "경남": "38", "제주": "50",
}
_DECL = re.compile(rb"""^\s*<\?xml[^>]*encoding=["']([A-Za-z0-9_\-]+)["'][^>]*\?>""")


def _decode(data: bytes) -> str:
    m = _DECL.match(data)
    enc = (m.group(1).decode("ascii") if m else "utf-8").lower()
    if enc in ("euc-kr", "euckr", "ks_c_5601-1987"):
        enc = "cp949"
    body = data[m.end():] if m else data
    return body.decode(enc, errors="replace")


def parse_items(xml: bytes) -> list[dict]:
    root = ET.fromstring(_decode(xml))
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]


def _coord(v: str) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f != 0 else None


def to_place(item: dict) -> Place:
    return Place(
        kind="heritage",
        name=item.get("ccbaMnm1", ""),
        source="khs",
        source_id=f"{item.get('ccbaKdcd', '')}-{item.get('ccbaAsno', '')}-{item.get('ccbaCtcd', '')}",
        lat=_coord(item.get("latitude")),
        lon=_coord(item.get("longitude")),
        address=item.get("ccbaLcad", "") or item.get("ccsiName", ""),
        # 국가유산청 목록에는 관람시간이 없음 → None (TourAPI 소개정보로 보충, 없으면 NO_HOURS)
    )


def search_heritage(region: str, kind: str = "국보", limit: int = 30) -> dict:
    if not region:
        return fail(Err.BAD_ARGUMENT, "region(시도 이름)은 필수입니다.")
    sido = SIDO.get(region[:2])
    if sido is None:
        return fail(Err.BAD_ARGUMENT, f"알 수 없는 시도입니다: {region}")
    params = {"ccbaKdcd": KIND.get(kind, "11"), "ccbaCtcd": sido, "pageUnit": limit, "pageIndex": 1}
    try:
        items = parse_items(get(LIST_URL, params=params, as_json=False))
    except ApiError as e:
        return fail(e.code, e.message)
    except ET.ParseError:
        return fail(Err.UPSTREAM_ERROR, "국가유산청 응답을 해석하지 못했습니다.")
    items = [i for i in items if i.get("ccbaCncl", "N") != "Y"]  # 지정 해제 제외
    if not items:
        return fail(Err.NO_PLACE, f"{region}에서 {kind}를 찾지 못했습니다.")
    places = [to_place(i) for i in items]
    return ok({"places": [p.to_dict() for p in places], "no_coord": sum(not p.has_coord for p in places)})
