from app.constraints.context import Context
from app.constraints.subject_rules import check_h4, check_h8, check_h9, check_h10
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, department=Department.MANAGEMENT, **kwargs):
    base = dict(
        name=code, base_name=code, department=department, year=1, term=Term.SPRING,
        quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_h4_requires_identical_slots_for_joint_pair():
    a = make("A1", department=Department.ACCOUNTING, joint_id="J001")
    b = make("B1", department=Department.MANAGEMENT, joint_id="J001")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert check_h4(ctx, tt, b, (TimeSlot("月", 1),)) == []
    assert [v.rule_id for v in check_h4(ctx, tt, b, (TimeSlot("火", 1),))] == ["H4"]


def test_h4_ignores_subject_without_joint_id():
    a = make("A1")
    ctx = Context.from_lists([a], [])
    assert check_h4(ctx, Timetable(), a, (TimeSlot("月", 1),)) == []


def test_h8_junior_remote_must_be_friday():
    subject = make("J1", department=Department.JUNIOR, is_remote=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h8(ctx, tt, subject, (TimeSlot("金", 1),)) == []
    assert [v.rule_id for v in check_h8(ctx, tt, subject, (TimeSlot("木", 1),))] == ["H8"]


def test_h8_junior_non_remote_is_unconstrained():
    subject = make("J2", department=Department.JUNIOR, is_remote=False)
    ctx = Context.from_lists([subject], [])
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("木", 1),)) == []


def test_h8_university_remote_must_be_friday():
    # 学科によらず、遠隔=○ は金曜に置く
    subject = make("A1", department=Department.ACCOUNTING, is_remote=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h8(ctx, tt, subject, (TimeSlot("金", 1),)) == []
    assert [v.rule_id for v in check_h8(ctx, tt, subject, (TimeSlot("木", 1),))] == ["H8"]


def test_h8_management_remote_must_be_friday():
    subject = make("B1", department=Department.MANAGEMENT, is_remote=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h8(ctx, tt, subject, (TimeSlot("金", 3),)) == []
    assert [v.rule_id for v in check_h8(ctx, tt, subject, (TimeSlot("月", 3),))] == ["H8"]


def test_h8_university_non_remote_is_unconstrained_by_default():
    # FRIDAY_IS_REMOTE_ONLY は既定で無効なので、対面科目はどこでも置ける
    subject = make("A1", department=Department.ACCOUNTING, is_remote=False)
    ctx = Context.from_lists([subject], [])
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("金", 1),)) == []
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("月", 1),)) == []


def test_h8_friday_is_remote_only_flag_blocks_face_to_face_on_friday():
    # 将来の切り替え用フラグ。有効にすると対面科目が金曜に置けなくなる
    from app.constraints import subject_rules

    subject = make("A1", department=Department.ACCOUNTING, is_remote=False)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    original = subject_rules.FRIDAY_IS_REMOTE_ONLY
    subject_rules.FRIDAY_IS_REMOTE_ONLY = True
    try:
        assert [v.rule_id for v in check_h8(ctx, tt, subject, (TimeSlot("金", 1),))] == ["H8"]
        assert check_h8(ctx, tt, subject, (TimeSlot("月", 1),)) == []
    finally:
        subject_rules.FRIDAY_IS_REMOTE_ONLY = original


def test_h9_fixed_slot_must_match():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h9(ctx, tt, subject, (TimeSlot("火", 3),)) == []
    assert [v.rule_id for v in check_h9(ctx, tt, subject, (TimeSlot("水", 3),))] == ["H9"]


def test_h9_without_fixed_slot_is_unconstrained():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    assert check_h9(ctx, Timetable(), subject, (TimeSlot("水", 3),)) == []


def test_h10_slot_count_must_match():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert [v.rule_id for v in check_h10(ctx, tt, subject, (TimeSlot("水", 2),))] == ["H10"]


def test_h10_consecutive_pair_is_valid():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h10(ctx, tt, subject, (TimeSlot("水", 2), TimeSlot("水", 3))) == []


def test_h10_rejects_non_consecutive_when_required():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("水", 2), TimeSlot("水", 4))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]


def test_h10_rejects_different_days_when_consecutive_required():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("水", 2), TimeSlot("木", 3))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]


def test_h10_allows_separate_days_when_not_consecutive_required():
    subject = make("J10405", slots_required=2, requires_consecutive=False)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h10(ctx, tt, subject, (TimeSlot("火", 2), TimeSlot("木", 2))) == []


def test_h10_rejects_duplicate_slots():
    subject = make("J1", slots_required=2, requires_consecutive=False)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("火", 2), TimeSlot("火", 2))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]
