import pytest

from app.constraints.context import Context, Violation
from app.constraints.teacher_rules import check_h1, check_h5, check_h6, check_h7
from app.models.enums import Category, Department, Quarter, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make_subject(code, teacher="教員甲", term=Term.SPRING, quarter=None, year=1,
                 department=Department.MANAGEMENT, category=Category.REQUIRED):
    return Subject(
        code=code, name=code, base_name=code, department=department, year=year,
        term=term, quarter=quarter, category=category, teacher=teacher,
    )


def build(subjects, teachers):
    return Context.from_lists(subjects, teachers)


def test_h1_flags_same_teacher_in_same_slot():
    a, b = make_subject("A1"), make_subject("B1")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    violations = check_h1(ctx, tt, b, (TimeSlot("月", 1),))
    assert [v.rule_id for v in violations] == ["H1"]
    assert violations[0].related_code == "A1"


def test_h1_allows_different_teachers():
    a = make_subject("A1", teacher="教員甲")
    b = make_subject("B1", teacher="教員乙")
    ctx = build([a, b], [
        Teacher("教員甲", TeacherKind.FULL_TIME),
        Teacher("教員乙", TeacherKind.FULL_TIME),
    ])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_allows_non_overlapping_quarters():
    a = make_subject("A1", term=Term.SPRING, quarter=Quarter.Q1)
    b = make_subject("B1", term=Term.SPRING, quarter=Quarter.Q2)
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_ignores_the_subjects_own_existing_placement():
    a = make_subject("A1")
    ctx = build([a], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, a, (TimeSlot("月", 1),)) == []


def test_h5_part_time_must_use_available_slots():
    a = make_subject("A1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME,
                      available_slots={TimeSlot("月", 2), TimeSlot("月", 3)})
    ctx = build([a], [teacher])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("月", 2),)) == []
    assert [v.rule_id for v in check_h5(ctx, tt, a, (TimeSlot("火", 2),))] == ["H5"]


def test_h5_part_time_without_availability_is_unconstrained():
    a = make_subject("A1", teacher="非常勤甲")
    ctx = build([a], [Teacher("非常勤甲", TeacherKind.PART_TIME)])
    assert check_h5(ctx, Timetable(), a, (TimeSlot("火", 2),)) == []


def test_h5_special_teacher_is_constrained_by_day_only():
    a = make_subject("A1", teacher="特任甲")
    teacher = Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水", "木"})
    ctx = build([a], [teacher])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("水", 5),)) == []
    assert [v.rule_id for v in check_h5(ctx, tt, a, (TimeSlot("金", 1),))] == ["H5"]


def test_h6_blocks_research_day():
    a = make_subject("A1", teacher="専任甲")
    ctx = build([a], [Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")])
    tt = Timetable()
    assert [v.rule_id for v in check_h6(ctx, tt, a, (TimeSlot("火", 1),))] == ["H6"]
    assert check_h6(ctx, tt, a, (TimeSlot("水", 1),)) == []


def test_h6_ignores_teacher_without_research_day():
    a = make_subject("A1", teacher="特任甲")
    ctx = build([a], [Teacher("特任甲", TeacherKind.SPECIAL, available_days={"火"})])
    assert check_h6(ctx, Timetable(), a, (TimeSlot("火", 1),)) == []


def test_h7_blocks_three_consecutive_periods():
    a, b, c = make_subject("A1"), make_subject("A2"), make_subject("A3")
    ctx = build([a, b, c], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)
    assert [v.rule_id for v in check_h7(ctx, tt, c, (TimeSlot("月", 3),))] == ["H7"]


def test_h7_allows_two_consecutive_periods():
    a, b = make_subject("A1"), make_subject("A2")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, b, (TimeSlot("月", 2),)) == []


def test_h7_allows_gap():
    a, b, c = make_subject("A1"), make_subject("A2"), make_subject("A3")
    ctx = build([a, b, c], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, c, (TimeSlot("月", 4),)) == []


def test_h7_allows_double_slot_subject_occupying_two_periods():
    double = make_subject("J1")
    double.slots_required = 2
    double.requires_consecutive = True
    ctx = build([double], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    assert check_h7(ctx, tt, double, (TimeSlot("水", 2), TimeSlot("水", 3))) == []


def test_unknown_teacher_is_unconstrained():
    a = make_subject("A1", teacher="未登録")
    ctx = build([a], [])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("金", 1),)) == []
    assert check_h6(ctx, tt, a, (TimeSlot("金", 1),)) == []
