"""Tool 등록 (F3001). Agent 에는 registry.catalog() 의 이름 · 설명 · 입력 스키마만 넘긴다.

설명에는 기능이 아니라 '언제 쓰는지'를 적는다 (명세서 2.3절).
"""

from __future__ import annotations

from .base import Tool, ToolRegistry
from .content import get_videos, make_insta_links
from .environment import get_crowd, get_holidays, get_weather
from .heritage import search_heritage
from .place import search_place
from .rag import ask_heritage
from .tour import get_visit_info, search_tour
from .transport import plan_leg

_point = {"type": "object", "properties": {"name": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}}}

registry = ToolRegistry()
for t in [
    Tool("search_heritage", "여행 지역에서 국보·보물·사적 후보가 필요할 때 부른다. 좌표가 함께 온다.",
         {"type": "object", "properties": {"region": {"type": "string", "description": "시도 이름 (예: 경북)"},
                                           "kind": {"type": "string", "enum": ["국보", "보물", "사적"]},
                                           "limit": {"type": "integer"}}, "required": ["region"]},
         search_heritage, tags=["F3002"]),
    Tool("search_tour", "어떤 지점 주변의 관광지·문화시설·축제·음식점·숙박 후보가 필요할 때 부른다.",
         {"type": "object", "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                           "kind": {"type": "string", "enum": ["attraction", "culture", "festival", "restaurant", "lodging"]},
                                           "radius_m": {"type": "integer"}}, "required": ["lat", "lon"]},
         search_tour, tags=["F3002"]),
    Tool("search_place", "TourAPI 에 없는 카페나 음식점을 동선 근처에서 보충해야 할 때 부른다. 영업시간은 주지 않는다.",
         {"type": "object", "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                           "kind": {"type": "string", "enum": ["cafe", "restaurant", "attraction", "culture"]},
                                           "radius_m": {"type": "integer"}}, "required": ["lat", "lon"]},
         search_place, tags=["F3002"]),
    Tool("get_visit_info", "후보 장소의 관람·영업시간, 쉬는 날, 입장료를 확인해 방문 가능 여부를 판정해야 할 때 부른다.",
         {"type": "object", "properties": {"content_id": {"type": "string"},
                                           "kind": {"type": "string", "enum": ["attraction", "culture", "festival", "restaurant", "lodging"]}},
          "required": ["content_id"]},
         get_visit_info, tags=["F3003"]),
    Tool("plan_leg", "두 지점 사이를 사용자가 고른 이동 수단으로 언제 어디서 타고 얼마나 걸리는지 알아야 할 때 부른다.",
         {"type": "object", "properties": {"mode": {"type": "string", "enum": ["train", "express", "intercity", "car", "transit"]},
                                           "origin": _point, "destination": _point,
                                           "date": {"type": "string", "description": "YYYY-MM-DD"},
                                           "depart_after": {"type": "string", "description": "HH:MM"}},
          "required": ["mode", "origin", "destination"]},
         plan_leg, tags=["F3004"]),
    Tool("get_weather", "여행 날짜·지역의 강수확률과 기온으로 야외·실내 비중을 정해야 할 때 부른다.",
         {"type": "object", "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}, "date": {"type": "string"}},
          "required": ["lat", "lon", "date"]},
         get_weather, tags=["F3004"]),
    Tool("get_holidays", "여행 날짜가 공휴일인지 알아야 할 때(휴관일 판정) 부른다.",
         {"type": "object", "properties": {"year": {"type": "integer"}, "month": {"type": "integer"}}, "required": ["year", "month"]},
         get_holidays, tags=["F3004"]),
    Tool("get_crowd", "관광지가 붐비는 시간대를 피해 방문 순서를 정해야 할 때 부른다.",
         {"type": "object", "properties": {"area_code": {"type": "string"}, "date": {"type": "string"}}, "required": ["area_code", "date"]},
         get_crowd, tags=["F3004"]),
    Tool("get_videos", "일정에 들어간 장소의 참고 영상을 보여 줄 때 부른다. 판단 근거로 쓰지 않는다.",
         {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]},
         get_videos, tags=["content"]),
    Tool("make_insta_links", "일정의 장소·지역 Instagram 해시태그 링크를 붙일 때 부른다.",
         {"type": "object", "properties": {"place_names": {"type": "array", "items": {"type": "string"}}, "region": {"type": "string"}},
          "required": ["place_names"]},
         make_insta_links, kind="local", tags=["content"]),
    Tool("ask_heritage", "국가유산에 대한 설명·역사·지정 이유를 근거와 함께 답해야 할 때 부른다.",
         {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
         ask_heritage, kind="local", tags=["F3022"]),
]:
    registry.register(t)

__all__ = ["registry", "Tool", "ToolRegistry"]
