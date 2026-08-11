"""教員 1 名を表すデータクラス。仕様書 §5.2 に対応する。"""
from dataclasses import dataclass, field

from app.models.enums import TeacherKind
from app.models.timeslot import TimeSlot


@dataclass(slots=True)
class Teacher:
    name: str
    """正規化済み氏名。"""

    kind: TeacherKind
    research_day: str | None = None
    """研究日。専任のみ設定される。"""

    available_days: set[str] = field(default_factory=set)
    """出勤可能曜日。特任のみ設定される。空集合なら制約なし。"""

    available_slots: set[TimeSlot] = field(default_factory=set)
    """出勤可能コマ。非常勤のみ設定される。空集合なら制約なし。"""
