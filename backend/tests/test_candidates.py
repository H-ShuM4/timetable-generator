from app.constraints.context import Context
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import candidate_slot_sets, feasible_slot_sets


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_single_slot_subject_has_25_candidates():
    assert len(candidate_slot_sets(make("A1"))) == 25


def test_fixed_slot_subject_has_exactly_one_candidate():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    assert candidate_slot_sets(subject) == [(TimeSlot("火", 3),)]


def test_consecutive_double_subject_has_20_candidates():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    candidates = candidate_slot_sets(subject)
    # 5 曜日 × 連続ペア 4 通り
    assert len(candidates) == 20
    assert (TimeSlot("月", 1), TimeSlot("月", 2)) in candidates
    assert (TimeSlot("月", 1), TimeSlot("月", 3)) not in candidates


def test_non_consecutive_double_subject_enumerates_all_pairs():
    subject = make("J2", slots_required=2, requires_consecutive=False)
    candidates = candidate_slot_sets(subject)
    assert len(candidates) == 300  # 25 から 2 つ選ぶ組合せ
    assert (TimeSlot("火", 2), TimeSlot("木", 2)) in candidates


def test_intensive_subject_has_no_candidates():
    assert candidate_slot_sets(make("A1", is_intensive=True)) == []


def test_feasible_filters_by_constraints():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    feasible = feasible_slot_sets(ctx, tt, b)
    assert (TimeSlot("月", 1),) not in feasible
    assert (TimeSlot("月", 2),) in feasible
    assert len(feasible) == 24
