from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.solver import solve


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=f"教員{code}",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_places_a_single_subject():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert solve(ctx, tt, ["A1"]) == []
    assert tt.is_placed("A1")


def test_result_has_no_violations():
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(5)]
    ctx = Context.from_lists(subjects, [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    assert solve(ctx, tt, [s.code for s in subjects]) == []
    assert validate_all(ctx, tt) == []


def test_reports_unplaced_when_no_solution_exists():
    # 同一教員・同一学科年次の必修が 26 件。25 コマしかないので 1 件は置けない
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(26)]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    unplaced = solve(ctx, tt, [s.code for s in subjects])
    assert len(unplaced) >= 1
    assert len(tt.placed_codes()) + len(unplaced) == 26
    assert validate_all(ctx, tt) == []


def test_respects_existing_placements():
    a, b = make("A1", teacher="教員甲"), make("B1", teacher="教員甲")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert solve(ctx, tt, ["B1"]) == []
    assert tt.slot_of("B1") != (TimeSlot("月", 1),)
    assert tt.assignments["A1"].source is AssignmentSource.PRELOCK


def test_marks_source_as_solver():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    solve(ctx, tt, ["A1"])
    assert tt.assignments["A1"].source is AssignmentSource.SOLVER


def test_places_consecutive_double_slot_subject():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert solve(ctx, tt, ["J1"]) == []
    slots = tt.slot_of("J1")
    assert len(slots) == 2
    assert slots[0].day == slots[1].day
    assert abs(slots[0].period - slots[1].period) == 1


def test_solves_tightly_constrained_pair():
    # 非常勤甲は金1のみ。必修同士なので同じコマには置けない。
    # 候補の少ない A1 を先に確定させないと解けない配置
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤乙")
    ctx = Context.from_lists([a, b], [
        Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)}),
        Teacher("非常勤乙", TeacherKind.PART_TIME,
                available_slots={TimeSlot("金", 1), TimeSlot("金", 2)}),
    ])
    tt = Timetable()
    assert solve(ctx, tt, ["B1", "A1"]) == []
    assert tt.slot_of("A1") == (TimeSlot("金", 1),)
    assert tt.slot_of("B1") == (TimeSlot("金", 2),)


def test_terminates_on_node_limit():
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(26)]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    unplaced = solve(ctx, tt, [s.code for s in subjects], node_limit=50)
    assert len(tt.placed_codes()) + len(unplaced) == 26
