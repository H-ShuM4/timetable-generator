"""配置の好み。制約ではないので、望ましくない候補も選べる。"""
from app.constraints.context import Context
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.preference import best_option, placement_preference


def make(code, department=Department.MANAGEMENT, adjacent_id=None, year=1):
    return Subject(
        code=code, name=code, base_name=code, department=department, year=year,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
        adjacent_id=adjacent_id,
    )


def test_periods_one_to_four_beat_period_five():
    subject = make("A1")
    chosen = best_option(Timetable(), subject, [(TimeSlot("月", 5),), (TimeSlot("月", 3),)])
    assert chosen == (TimeSlot("月", 3),)


def test_period_five_is_used_when_nothing_else_is_offered():
    """好みであって制約ではない。5 限しか無ければ 5 限に置く。"""
    subject = make("A1")
    assert best_option(Timetable(), subject, [(TimeSlot("月", 5),)]) == (TimeSlot("月", 5),)


def test_an_adjacent_partner_pulls_the_subject_next_to_it():
    third = make("T1", adjacent_id="N001", year=3)
    fourth = make("F1", adjacent_id="N001", year=4)
    ctx = Context.from_lists([third, fourth], [])
    tt = Timetable()
    tt.place("T1", (TimeSlot("水", 2),), AssignmentSource.SOLVER)

    options = [(TimeSlot("水", 4),), (TimeSlot("水", 3),), (TimeSlot("木", 1),)]
    assert best_option(tt, fourth, options, ctx) == (TimeSlot("水", 3),)


def test_the_same_day_beats_a_closer_period_on_another_day():
    third = make("T1", adjacent_id="N001", year=3)
    fourth = make("F1", adjacent_id="N001", year=4)
    ctx = Context.from_lists([third, fourth], [])
    tt = Timetable()
    tt.place("T1", (TimeSlot("水", 1),), AssignmentSource.SOLVER)

    assert best_option(tt, fourth, [(TimeSlot("木", 2),), (TimeSlot("水", 4),)], ctx) == (
        TimeSlot("水", 4),
    )


def test_avoiding_period_five_outranks_adjacency():
    third = make("T1", adjacent_id="N001", year=3)
    fourth = make("F1", adjacent_id="N001", year=4)
    ctx = Context.from_lists([third, fourth], [])
    tt = Timetable()
    tt.place("T1", (TimeSlot("水", 4),), AssignmentSource.SOLVER)

    # 水5 なら隣接するが 5 限。木1 は離れるが 1〜4 限。
    assert best_option(tt, fourth, [(TimeSlot("水", 5),), (TimeSlot("木", 1),)], ctx) == (
        TimeSlot("木", 1),
    )


def test_adjacency_is_ignored_without_a_context():
    subject = make("A1", adjacent_id="N001")
    assert placement_preference(Timetable(), subject, (TimeSlot("月", 1),))[1] == 0


def test_adjacency_is_ignored_when_the_partner_is_unplaced():
    third = make("T1", adjacent_id="N001", year=3)
    fourth = make("F1", adjacent_id="N001", year=4)
    ctx = Context.from_lists([third, fourth], [])
    assert placement_preference(Timetable(), fourth, (TimeSlot("月", 1),), ctx)[1] == 0
