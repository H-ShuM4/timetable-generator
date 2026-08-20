"""配置結果を保持する。制約検証・ソルバー・API が共有する唯一の状態。"""
from dataclasses import dataclass, field
from enum import Enum

from app.models.timeslot import TimeSlot


class AssignmentSource(str, Enum):
    """そのコマを誰が決めたか。フロントの色分けに使う。"""

    PRELOCK = "prelock"
    GEMINI = "gemini"
    SOLVER = "solver"
    MANUAL = "manual"
    INHERITED = "inherited"


@dataclass(frozen=True, slots=True)
class Assignment:
    subject_code: str
    slots: tuple[TimeSlot, ...]
    source: AssignmentSource


@dataclass(slots=True)
class Timetable:
    assignments: dict[str, Assignment] = field(default_factory=dict)
    _by_slot: dict[TimeSlot, list[str]] = field(default_factory=dict)
    version: int = 0
    """配置が変わるたびに増える。走査結果を再利用してよいかの判断に使う。"""

    def place(
        self, code: str, slots: tuple[TimeSlot, ...], source: AssignmentSource
    ) -> None:
        if code in self.assignments:
            raise ValueError(f"科目 {code} は既に配置されています")
        self.assignments[code] = Assignment(code, slots, source)
        for slot in slots:
            self._by_slot.setdefault(slot, []).append(code)
        self.version += 1

    def remove(self, code: str) -> None:
        assignment = self.assignments.pop(code, None)
        if assignment is None:
            return
        for slot in assignment.slots:
            holders = self._by_slot.get(slot)
            if holders and code in holders:
                holders.remove(code)
        self.version += 1

    def occupied_by(self, slot: TimeSlot) -> list[str]:
        return list(self._by_slot.get(slot, []))

    def slot_of(self, code: str) -> tuple[TimeSlot, ...]:
        assignment = self.assignments.get(code)
        return assignment.slots if assignment else ()

    def is_placed(self, code: str) -> bool:
        return code in self.assignments

    def placed_codes(self) -> set[str]:
        return set(self.assignments)
