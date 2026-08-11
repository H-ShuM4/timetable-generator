"""制約評価に必要な索引をまとめる。ルール関数は必ずこれを受け取る。"""
from dataclasses import dataclass

from app.constraints.period_overlap import periods_overlap
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


@dataclass(frozen=True, slots=True)
class Violation:
    rule_id: str
    subject_code: str
    message: str
    related_code: str | None = None


@dataclass(slots=True)
class Context:
    subjects: dict[str, Subject]
    teachers: dict[str, Teacher]

    @classmethod
    def from_lists(
        cls, subjects: list[Subject], teachers: list[Teacher] | dict[str, Teacher]
    ) -> "Context":
        teacher_map = (
            teachers if isinstance(teachers, dict)
            else {teacher.name: teacher for teacher in teachers}
        )
        return cls({s.code: s for s in subjects}, teacher_map)


def others_at(
    context: Context, timetable: Timetable, slot: TimeSlot, exclude_code: str
) -> list[Subject]:
    """slot を占める他科目のうち、exclude_code の科目と開講期間が重なるもの。"""
    target = context.subjects[exclude_code]
    result: list[Subject] = []
    for code in timetable.occupied_by(slot):
        if code == exclude_code:
            continue
        other = context.subjects.get(code)
        if other is None:
            continue
        if periods_overlap(target.term, target.quarter, other.term, other.quarter):
            result.append(other)
    return result
