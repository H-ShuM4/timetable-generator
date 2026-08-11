"""教員に関する制約 H1・H5・H6・H7。

すべて「subject を slots に置いたら違反するか」を返す。timetable 上の
subject 自身の既存配置は無視する。
"""
from app.constraints.context import Context, Violation, others_at
from app.constraints.period_overlap import periods_overlap
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

MAX_CONSECUTIVE = 2
"""同一教員が同一日に連続してよいコマ数の上限。"""


def check_h1(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同曜日・同時限に別科目を持たない（全学科横断）。"""
    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if other.teacher and other.teacher == subject.teacher:
                violations.append(Violation(
                    rule_id="H1",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} が {slot} に "
                        f"{other.name} と重複しています"
                    ),
                    related_code=other.code,
                ))
    return violations


def check_h5(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """非常勤は出勤可能コマのみ、特任は出勤可能曜日のみ。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None:
        return []

    violations: list[Violation] = []
    if teacher.kind is TeacherKind.PART_TIME and teacher.available_slots:
        for slot in slots:
            if slot not in teacher.available_slots:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot} に出勤できません",
                ))
    if teacher.kind is TeacherKind.SPECIAL and teacher.available_days:
        for slot in slots:
            if slot.day not in teacher.available_days:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot.day}曜日に出勤できません",
                ))
    return violations


def check_h6(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """専任の研究日には配置しない。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None or not teacher.research_day:
        return []
    return [
        Violation(
            rule_id="H6",
            subject_code=subject.code,
            message=f"{teacher.name} の研究日（{teacher.research_day}曜日）です",
        )
        for slot in slots
        if slot.day == teacher.research_day
    ]


def _periods_on_day(
    context: Context, timetable: Timetable, subject: Subject, day: str
) -> set[int]:
    """その日に subject の担当教員が持つ時限。subject 自身の既存配置は除く。"""
    periods: set[int] = set()
    if not subject.teacher:
        return periods
    for code, assignment in timetable.assignments.items():
        if code == subject.code:
            continue
        other = context.subjects.get(code)
        if other is None or other.teacher != subject.teacher:
            continue
        if not periods_overlap(subject.term, subject.quarter, other.term, other.quarter):
            continue
        periods.update(slot.period for slot in assignment.slots if slot.day == day)
    return periods


def check_h7(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同一日に 3 コマ以上連続しない。"""
    violations: list[Violation] = []
    for day in {slot.day for slot in slots}:
        occupied = _periods_on_day(context, timetable, subject, day)
        occupied.update(slot.period for slot in slots if slot.day == day)

        run = 0
        for period in sorted(occupied):
            run = run + 1 if (period - 1) in occupied else 1
            if run > MAX_CONSECUTIVE:
                violations.append(Violation(
                    rule_id="H7",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} の {day}曜日が "
                        f"{MAX_CONSECUTIVE + 1} コマ以上連続します"
                    ),
                ))
                break
    return violations


TEACHER_RULES = (check_h1, check_h5, check_h6, check_h7)
