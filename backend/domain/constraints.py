"""판정 엔진 — 제약 판단은 모두 코드로 한다 (F3008).

LLM 은 조건 추출 · 운영시간 문장 해석 · 대안 선택만 맡고,
아래 함수들이 통과 여부를 정한다. 외부 API 로 확인할 수 없는 값(체류시간 등)은
지어내지 않고 역산한 기준을 돌려준다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from backend.tools.base import Err

from .place import Place

LUNCH = (time(11, 30), time(13, 30))
DINNER = (time(17, 30), time(19, 30))


@dataclass
class BudgetResult:
    ok: bool
    available_min: int  # 출발~복귀편 사이 쓸 수 있는 시간
    travel_min: int  # 이동 합계
    fixed_stay_min: int  # 사용자가 정한 체류시간 합계
    max_stay_each_min: int | None  # 체류시간이 정해지지 않은 장소의 '곳당 최대' (역산값)
    shortage_min: int  # 모자라는 시간 (ok 면 0)


def check_time_budget(
    start: datetime,
    deadline: datetime,
    legs_min: list[int],
    stays_min: list[int | None],
    min_stay_min: int = 20,
) -> BudgetResult:
    """출발 + Σ이동 + Σ체류 ≤ 복귀편 출발.

    체류시간이 없는 장소(None)는 남는 시간을 똑같이 나눈 '곳당 최대 N분'으로 역산한다.
    그 값이 min_stay_min 보다 작으면 실패로 본다.
    """
    available = int((deadline - start).total_seconds() // 60)
    travel = sum(legs_min)
    fixed = sum(s for s in stays_min if s is not None)
    unknown = sum(1 for s in stays_min if s is None)
    remaining = available - travel - fixed
    if unknown:
        each = remaining // unknown if remaining > 0 else 0
        ok_ = each >= min_stay_min
        shortage = 0 if ok_ else min_stay_min * unknown - max(remaining, 0)
        return BudgetResult(ok_, available, travel, fixed, each, shortage)
    return BudgetResult(remaining >= 0, available, travel, fixed, None, max(0, -remaining))


def in_window(t: time, window: tuple[time, time]) -> bool:
    return window[0] <= t <= window[1]


def intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """[a_start, a_end) 와 [b_start, b_end) 가 겹치는지 (F3015 계획 겹침)."""
    return a_start < b_end and b_start < a_end


def check_open(place: Place, arrive: datetime, leave: datetime, holidays: set[date] | None = None) -> tuple[bool, str | None]:
    """도착~출발이 운영시간 안이고 쉬는 날이 아닌지. 실패면 (False, 코드)."""
    day = arrive.date()
    if arrive.weekday() in place.closed_weekdays:
        return False, Err.CLOSED
    if place.closed_on_holidays and holidays and day in holidays:
        return False, Err.CLOSED
    if place.open_time is None or place.close_time is None:
        # 상시 개방 여부를 모르면 판정하지 않는다 (지어내지 않음)
        return False, Err.NO_HOURS
    if not (place.open_time <= arrive.time() and leave.time() <= place.close_time):
        return False, Err.CLOSED
    return True, None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이 직선거리(km). 후보를 동선 순으로 대략 정렬할 때만 쓴다 — 이동시간 판정에는 쓰지 않음."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def add_min(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)
