from app.constraints.context import Context
from app.models.enums import TeacherKind
from app.models.teacher import Teacher
from tests.factories import subject as make
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource
from app.scheduler.prelock import prelock




def test_fixed_slot_subject_is_locked():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    ctx = Context.from_lists([subject], [])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.slot_of("A1") == (TimeSlot("火", 3),)
    assert timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    assert unplaced == []


def test_intensive_subject_is_not_placed():
    subject = make("A1", is_intensive=True)
    ctx = Context.from_lists([subject], [])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_part_time_subject_is_placed_in_available_slot():
    subject = make("A1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)})
    ctx = Context.from_lists([subject], [teacher])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.slot_of("A1") == (TimeSlot("金", 1),)
    assert unplaced == []


def test_full_time_and_special_subjects_are_left_for_later_stages():
    a = make("A1", teacher="専任甲")
    b = make("B1", teacher="特任甲")
    ctx = Context.from_lists([a, b], [
        Teacher("専任甲", TeacherKind.FULL_TIME, research_day="月"),
        Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水"}),
    ])
    timetable, unplaced = prelock(ctx, [a, b])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_part_time_without_availability_is_left_for_later_stages():
    subject = make("A1", teacher="非常勤甲")
    ctx = Context.from_lists([subject], [Teacher("非常勤甲", TeacherKind.PART_TIME)])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_conflicting_part_time_subjects_report_the_leftover():
    # 同一非常勤が同じ 1 コマしか出勤できないのに担当科目が 2 件
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)})
    ctx = Context.from_lists([a, b], [teacher])
    timetable, unplaced = prelock(ctx, [a, b])
    assert len(timetable.placed_codes()) == 1
    assert len(unplaced) == 1


def test_most_constrained_part_time_subject_is_placed_first():
    # A1 は 1 コマだけ、B1 は 2 コマ選べる。A1 を先に確定させれば両方置ける
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤乙")
    ctx = Context.from_lists([a, b], [
        Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)}),
        Teacher("非常勤乙", TeacherKind.PART_TIME,
                available_slots={TimeSlot("金", 1), TimeSlot("金", 2)}),
    ])
    timetable, unplaced = prelock(ctx, [b, a])
    assert timetable.slot_of("A1") == (TimeSlot("金", 1),)
    assert unplaced == []
