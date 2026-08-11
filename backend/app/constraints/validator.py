"""制約検証の唯一の入口。

Gemini の応答検証、ソルバーの枝刈り、フロントの D&D 編集判定は
すべてこのモジュールを経由する。ここを通らない検証を書いてはならない。
"""
from app.constraints.context import Context, Violation
from app.constraints.student_rules import STUDENT_RULES
from app.constraints.subject_rules import SUBJECT_RULES
from app.constraints.teacher_rules import TEACHER_RULES
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

ALL_RULES = TEACHER_RULES + STUDENT_RULES + SUBJECT_RULES


def check_placement(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """subject を slots に置いた場合の違反をすべて返す。

    timetable 上の subject 自身の既存配置は評価から除外される。
    """
    violations: list[Violation] = []
    for rule in ALL_RULES:
        violations.extend(rule(context, timetable, subject, slots))
    return violations


def is_allowed(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> bool:
    """1 件でも違反があれば False。ソルバーの枝刈りに使う。"""
    for rule in ALL_RULES:
        if rule(context, timetable, subject, slots):
            return False
    return True


def validate_all(context: Context, timetable: Timetable) -> list[Violation]:
    """完成した時間割を通しで検証する。違反は関係する両科目から報告される。"""
    violations: list[Violation] = []
    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        violations.extend(check_placement(context, timetable, subject, assignment.slots))
    return violations
