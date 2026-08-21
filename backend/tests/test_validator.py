from app.constraints.context import Context
from app.constraints.validator import ALL_RULES, check_placement, is_allowed, validate_all
from app.models.enums import TeacherKind
from app.models.teacher import Teacher
from tests.factories import subject as make
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable




def test_all_rules_covers_every_hard_constraint():
    """規則を足したらここに現れる。番号の抜けや重複にも気づけるようにする。"""
    # H11 は欠番。1 日の合計コマ数の上限として一度足したが、H7 の
    # 連続 3 コマ制限が 1 日 4 コマを含むため撤去した。番号は再利用
    # しない。過去のやり取りで H11 と呼んだものと別物になるため。
    assert sorted(rule.__name__ for rule in ALL_RULES) == sorted(
        f"check_h{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
    )


def test_check_placement_aggregates_multiple_rule_violations():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME, research_day="月")])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    ids = sorted(v.rule_id for v in check_placement(ctx, tt, b, (TimeSlot("月", 1),)))
    assert ids == ["H1", "H2", "H6"]


def test_is_allowed_is_false_when_any_rule_fires():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert is_allowed(ctx, tt, b, (TimeSlot("月", 1),)) is False
    assert is_allowed(ctx, tt, b, (TimeSlot("火", 1),)) is True


def test_validate_all_finds_violations_in_a_finished_timetable():
    # H2 だけを見たいので担当教員は別にする。同じ教員にすると H1 も同時に立つ
    a, b = make("A1", teacher="教員甲"), make("B1", teacher="教員乙")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    tt.place("B1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)

    violations = validate_all(ctx, tt)
    assert {v.rule_id for v in violations} == {"H2"}
    # 双方向で報告されるため 2 件
    assert len(violations) == 2


def test_validate_all_returns_empty_for_clean_timetable():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    tt.place("B1", (TimeSlot("火", 1),), AssignmentSource.GEMINI)
    assert validate_all(ctx, tt) == []


def test_h1_applies_even_when_the_teacher_is_absent_from_the_roster():
    # 名簿外教員の「制約なし」は H5・H6 の例外であって、二重予約は許されない
    a, b = make("A1", teacher="名簿外教員"), make("B1", teacher="名簿外教員")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)

    assert "H1" in {v.rule_id for v in check_placement(ctx, tt, b, (TimeSlot("月", 1),))}
