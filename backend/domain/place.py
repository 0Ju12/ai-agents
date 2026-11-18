"""통합 장소 형식.

국가유산청 · TourAPI · 카카오 로컬에서 온 후보를 모두 이 형식으로 바꿔
하나의 판정 엔진(constraints.py)에 넣는다. 확인할 수 없는 값은 None 으로 두고
임의로 채우지 않는다 (F3003, F3008).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import time
from typing import Literal

PlaceKind = Literal["heritage", "attraction", "culture", "festival", "restaurant", "cafe", "lodging"]
Source = Literal["khs", "tourapi", "kakao"]


@dataclass
class Place:
    kind: PlaceKind
    name: str
    source: Source
    source_id: str
    lat: float | None = None
    lon: float | None = None
    address: str = ""
    open_time: time | None = None  # 해석에 실패하면 None → NO_HOURS (판정 보류)
    close_time: time | None = None
    closed_weekdays: set[int] = field(default_factory=set)  # 0=월 … 6=일
    closed_on_holidays: bool = False
    hours_text: str = ""  # 원문 (해석 근거로 화면·로그에 함께 보여 줌)
    indoor: bool | None = None  # None = 실내·야외 불확실
    stay_min: int | None = None  # 사용자가 정한 체류시간. 없으면 역산
    url: str = ""

    @property
    def has_coord(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["open_time"] = self.open_time.strftime("%H:%M") if self.open_time else None
        d["close_time"] = self.close_time.strftime("%H:%M") if self.close_time else None
        d["closed_weekdays"] = sorted(self.closed_weekdays)
        return d
