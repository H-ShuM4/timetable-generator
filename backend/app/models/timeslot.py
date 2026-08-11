"""曜日と時限の組。時間割グリッドの座標を表す。"""
from dataclasses import dataclass

DAYS: tuple[str, ...] = ("月", "火", "水", "木", "金")
PERIODS: tuple[int, ...] = (1, 2, 3, 4, 5)

INTENSIVE_PERIOD = 99
"""集中講義を表す時限。グリッドには含めない。"""


@dataclass(frozen=True, slots=True)
class TimeSlot:
    day: str
    period: int

    def __str__(self) -> str:
        return f"{self.day}{self.period}"


def all_slots() -> list[TimeSlot]:
    """月1 から 金5 まで、曜日を外側にした 25 スロット。"""
    return [TimeSlot(day, period) for day in DAYS for period in PERIODS]
