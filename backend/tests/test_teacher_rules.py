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


def test_h1_exempts_joint_pairs():
    # 合同ペアは物理的に1つの授業。H4 が同一コマを要求するため H1 は無視する
    a = make_subject("A1", department=Department.ACCOUNTING)
    b = make_subject("B1", department=Department.MANAGEMENT)
    a.joint_id = b.joint_id = "J001"
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_still_flags_a_different_joint_group():
    a = make_subject("A1", department=Department.ACCOUNTING)
    b = make_subject("B1", department=Department.MANAGEMENT)
    a.joint_id = "J001"
    b.joint_id = "J002"
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert [v.rule_id for v in check_h1(ctx, tt, b, (TimeSlot("月", 1),))] == ["H1"]


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


def test_h7_blocks_four_consecutive_periods():
    subjects = [make_subject(f"A{n}") for n in range(1, 5)]
    ctx = build(subjects, [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    for n in (1, 2, 3):
        tt.place(f"A{n}", (TimeSlot("月", n),), AssignmentSource.PRELOCK)
    violations = check_h7(ctx, tt, ctx.subjects["A4"], (TimeSlot("月", 4),))
    assert [v.rule_id for v in violations] == ["H7"]


def test_h7_allows_three_consecutive_periods():
    """ゼミの隣接（課題研究＋卒業研究）に前後 1 コマ足せる余地を残す。"""
    a, b, c = make_subject("A1"), make_subject("A2"), make_subject("A3")
    ctx = build([a, b, c], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, c, (TimeSlot("月", 3),)) == []


def test_h7_allows_two_consecutive_periods():
    a, b = make_subject("A1"), make_subject("A2")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, b, (TimeSlot("月", 2),)) == []


def test_h7_does_not_mix_courses_from_different_quarters():
    """後①と後②の科目は同時に開講されないので、一緒に数えてはいけない。

    実データで 水1（学期全体）・水2（後①）・水3（後②）が 3 コマ連続と
    誤検出された。実際には後期前半が水1・水2、後期後半が水1・水3 で、
    3 コマ連続する瞬間は無い。
    """
    whole = make_subject("A1", term=Term.FALL)
    first = make_subject("A2", term=Term.FALL, quarter=Quarter.Q3)
    second = make_subject("A3", term=Term.FALL, quarter=Quarter.Q4)
    ctx = build([whole, first, second], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A2", (TimeSlot("水", 2),), AssignmentSource.PRELOCK)
    tt.place("A3", (TimeSlot("水", 3),), AssignmentSource.PRELOCK)

    assert check_h7(ctx, tt, whole, (TimeSlot("水", 1),)) == []


def test_h7_still_flags_a_run_within_one_quarter():
    whole = make_subject("A1", term=Term.FALL)
    others = [make_subject(f"A{n}", term=Term.FALL, quarter=Quarter.Q3) for n in (2, 3, 4)]
    ctx = build([whole, *others], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    for n, period in ((2, 2), (3, 3), (4, 4)):
        tt.place(f"A{n}", (TimeSlot("水", period),), AssignmentSource.PRELOCK)

    # 後①には 水2・水3・水4 が立つので、水1 を足すと 4 コマ連続になる
    assert [v.rule_id for v in check_h7(ctx, tt, whole, (TimeSlot("水", 1),))] == ["H7"]


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


def test_h7_does_not_double_count_subjects_own_existing_placement():
    # A1 は月1に配置済み、教員甲はさらに月2にB1を持つ。この状態で
    # A1 を月3へ動かせるか再検証する（result.py の move は、新しい候補を
    # 検証する時点でまだ A1 自身の旧配置 [月1] を timetable から取り除いて
    # いない）。自身の旧配置を「他の科目」として数えてしまうと
    # 月1・月2・月3 の3コマ連続とみなし、誤って H7 違反を報告する。
    # 実際には A1 が月3へ移るのだから月1は空き、月2・月3の2コマ連続に
    # とどまり違反ではない。
    a, b = make_subject("A1"), make_subject("A2")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)

    assert check_h7(ctx, tt, a, (TimeSlot("月", 3),)) == []


def test_unknown_teacher_is_unconstrained():
    a = make_subject("A1", teacher="未登録")
    ctx = build([a], [])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("金", 1),)) == []
    assert check_h6(ctx, tt, a, (TimeSlot("金", 1),)) == []


def test_a_teacher_cannot_hold_five_periods_in_one_day():
    """1 日の合計コマ数に別の上限は要らない。H7 が自動的に含んでいる。

    時限は 1〜5 の 5 コマしかないので、5 コマ持つには全部を取るしかなく、
    それは 5 コマ連続になって H7 に触れる。
    """
    subjects = [make_subject(f"P{n}") for n in range(1, 6)]
    ctx = build(subjects, [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    for n in range(1, 5):
        tt.place(f"P{n}", (TimeSlot("月", n),), AssignmentSource.SOLVER)
    assert [v.rule_id for v in check_h7(ctx, tt, ctx.subjects["P5"], (TimeSlot("月", 5),))] == ["H7"]


def test_four_periods_a_day_are_allowed_when_they_are_not_all_in_a_row():
    subjects = [make_subject(f"P{n}") for n in (1, 2, 4, 5)]
    ctx = build(subjects, [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    for n in (1, 2, 4):
        tt.place(f"P{n}", (TimeSlot("月", n),), AssignmentSource.SOLVER)
    assert check_h7(ctx, tt, ctx.subjects["P5"], (TimeSlot("月", 5),)) == []
