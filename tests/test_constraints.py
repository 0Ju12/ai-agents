"""검증 4.2 — 제약 판정 계산과 '지어내지 않음'."""

from datetime import date, datetime, time

from backend.domain.constraints import LUNCH, check_open, check_time_budget, in_window, intervals_overlap
from backend.domain.place import Place
from backend.tools.base import Err

T = lambda h, m=0: datetime(2026, 11, 21, h, m)  # noqa: E731 — 토요일


def test_budget_with_fixed_stays():
    r = check_time_budget(T(10, 5), T(18, 30), legs_min=[50, 15, 30, 25], stays_min=[90, 60, 60])
    assert r.available_min == 505 and r.travel_min == 120 and r.ok and r.shortage_min == 0


def test_budget_back_calculates_stay_when_unknown():
    """체류시간을 모르면 지어내지 않고 '곳당 최대 N분'으로 역산."""
    r = check_time_budget(T(10, 5), T(18, 30), legs_min=[50, 15, 30, 25], stays_min=[None, None, None])
    assert r.ok and r.max_stay_each_min == (505 - 120) // 3


def test_budget_shortage():
    r = check_time_budget(T(10), T(12), legs_min=[60, 50], stays_min=[30])
    assert not r.ok and r.shortage_min == 20


def test_overlap_half_open():
    assert intervals_overlap(T(10), T(14), T(13), T(16))
    assert not intervals_overlap(T(10), T(13), T(13), T(16))  # 끝 = 시작이면 겹치지 않음


def test_lunch_window():
    assert in_window(time(12, 10), LUNCH) and not in_window(time(14, 0), LUNCH)


def test_check_open_rules():
    museum = Place("culture", "박물관", "tourapi", "1", open_time=time(10), close_time=time(18), closed_weekdays={0},
                   closed_on_holidays=True)
    monday = datetime(2026, 11, 23, 11)
    assert check_open(museum, monday, monday.replace(hour=12)) == (False, Err.CLOSED)
    assert check_open(museum, T(11), T(12)) == (True, None)
    assert check_open(museum, T(17), T(19)) == (False, Err.CLOSED)
    assert check_open(museum, T(11), T(12), holidays={date(2026, 11, 21)}) == (False, Err.CLOSED)
    cafe = Place("cafe", "카페", "kakao", "2")  # 카카오는 영업시간을 주지 않음
    assert check_open(cafe, T(15), T(16)) == (False, Err.NO_HOURS)
