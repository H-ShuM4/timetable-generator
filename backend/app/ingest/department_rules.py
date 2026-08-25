"""学科・年次ごとの編成規則。事務局が定めたもので、Excel には現れない。

いまのところ会計学科 1 年の 2 つを持つ。

- **朝学習**：月・火・木・金の 1 限は朝学習の時間なので授業を置かない
- **水曜の編成**：1 限から 4 限までどの科目が入るか事務局が決めている

規則を JSON に置いているのは、学年や学科が増えたときにコードを触らずに
足せるようにするためである。ファイルが無い・壊れている場合は規則なしと
して扱う。時間割が作れなくなるより、規則が効かないほうが害が小さい。
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.models.enums import Department
from app.models.subject import Subject
from app.models.timeslot import TimeSlot

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "department_rules.json"


@dataclass(slots=True)
class MorningStudy:
    """授業を置かない朝の時間帯。"""

    department: Department
    year: int
    days: frozenset[str]
    period: int

    def blocks(self, subject: Subject, slot: TimeSlot) -> bool:
        return (
            subject.department is self.department
            and subject.year == self.year
            and slot.period == self.period
            and slot.day in self.days
        )


@dataclass(slots=True)
class FixedDay:
    """曜日ごと編成が決まっている枠。"""

    department: Department
    year: int
    day: str
    periods: dict[str, int] = field(default_factory=dict)
    """base_name → 時限。"""

    ignore_consecutive_limit: bool = False
    """ここで固定したコマを、教員の連続コマ数に数えないか。"""

    def slot_for(self, subject: Subject) -> TimeSlot | None:
        if subject.department is not self.department or subject.year != self.year:
            return None
        period = self.periods.get(subject.base_name)
        return TimeSlot(self.day, period) if period else None


@dataclass(slots=True)
class DepartmentRules:
    morning_study: list[MorningStudy] = field(default_factory=list)
    fixed_days: list[FixedDay] = field(default_factory=list)

    def morning_study_blocks(self, subject: Subject, slot: TimeSlot) -> bool:
        return any(rule.blocks(subject, slot) for rule in self.morning_study)

    def fixed_slot_for(self, subject: Subject) -> TimeSlot | None:
        for rule in self.fixed_days:
            slot = rule.slot_for(subject)
            if slot is not None:
                return slot
        return None

    def exempt_from_consecutive_limit(self, subject: Subject, slot: TimeSlot) -> bool:
        """このコマを教員の連続コマ数に数えないか。

        「無視してよい」を教員まるごとに広げない。事務局が決めた枠だけを
        数から外し、同じ教員の他の授業は通常どおり数える。
        """
        for rule in self.fixed_days:
            if not rule.ignore_consecutive_limit:
                continue
            if rule.slot_for(subject) == slot:
                return True
        return False


def load_department_rules(path: Path | None = None) -> DepartmentRules:
    target = Path(path) if path else _CONFIG_PATH
    if not target.exists():
        return DepartmentRules()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return DepartmentRules(
            morning_study=[
                MorningStudy(
                    department=Department(item["department"]),
                    year=int(item["year"]),
                    days=frozenset(item["days"]),
                    period=int(item["period"]),
                )
                for item in raw.get("morning_study", [])
            ],
            fixed_days=[
                FixedDay(
                    department=Department(item["department"]),
                    year=int(item["year"]),
                    day=item["day"],
                    periods={
                        name: int(period)
                        for period, names in item.get("periods", {}).items()
                        for name in names
                    },
                    ignore_consecutive_limit=bool(item.get("ignore_consecutive_limit")),
                )
                for item in raw.get("fixed_days", [])
            ],
        )
    except (json.JSONDecodeError, ValueError, KeyError, TypeError, OSError):
        return DepartmentRules()


RULES = load_department_rules()
"""読み込み済みの規則。制約とリーダーが参照する。"""
