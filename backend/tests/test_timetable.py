import pytest

from app.models.timeslot import TimeSlot
from app.models.timetable import Assignment, AssignmentSource, Timetable


def test_place_and_lookup():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert t.is_placed("A001")
    assert t.slot_of("A001") == (TimeSlot("月", 1),)
    assert t.occupied_by(TimeSlot("月", 1)) == ["A001"]
    assert t.placed_codes() == {"A001"}


def test_multiple_subjects_can_share_a_slot():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    t.place("B001", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    assert sorted(t.occupied_by(TimeSlot("月", 1))) == ["A001", "B001"]


def test_two_slot_subject_occupies_both():
    t = Timetable()
    t.place("J159", (TimeSlot("水", 2), TimeSlot("水", 3)), AssignmentSource.SOLVER)
    assert t.occupied_by(TimeSlot("水", 2)) == ["J159"]
    assert t.occupied_by(TimeSlot("水", 3)) == ["J159"]


def test_remove_clears_all_slots():
    t = Timetable()
    t.place("J159", (TimeSlot("水", 2), TimeSlot("水", 3)), AssignmentSource.SOLVER)
    t.remove("J159")
    assert not t.is_placed("J159")
    assert t.occupied_by(TimeSlot("水", 2)) == []


def test_placing_same_code_twice_raises():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    with pytest.raises(ValueError, match="A001"):
        t.place("A001", (TimeSlot("火", 1),), AssignmentSource.GEMINI)


def test_assignment_records_source():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.MANUAL)
    assert t.assignments["A001"] == Assignment(
        "A001", (TimeSlot("月", 1),), AssignmentSource.MANUAL
    )
