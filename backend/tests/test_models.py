from app.models.enums import Department, Term, Quarter, Category, TeacherKind
from app.models.timeslot import TimeSlot, DAYS, PERIODS, all_slots


def test_department_values_match_excel():
    assert Department("経営") is Department.MANAGEMENT
    assert Department("会計") is Department.ACCOUNTING
    assert Department("短期大学部") is Department.JUNIOR


def test_days_and_periods():
    assert DAYS == ("月", "火", "水", "木", "金")
    assert PERIODS == (1, 2, 3, 4, 5)


def test_all_slots_has_25_entries():
    slots = all_slots()
    assert len(slots) == 25
    assert slots[0] == TimeSlot("月", 1)
    assert slots[-1] == TimeSlot("金", 5)


def test_timeslot_is_hashable_and_frozen():
    s = TimeSlot("火", 3)
    assert {s: 1}[TimeSlot("火", 3)] == 1


def test_enums_cover_categories_and_kinds():
    assert Category("必修") is Category.REQUIRED
    assert Category("選択必修") is Category.ELECTIVE_REQUIRED
    assert Category("選択") is Category.ELECTIVE
    assert Term("前期") is Term.SPRING
    assert Quarter("前①") is Quarter.Q1
    assert TeacherKind("非常勤") is TeacherKind.PART_TIME
