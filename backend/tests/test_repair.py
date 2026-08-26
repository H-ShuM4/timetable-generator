"""Stage 5.5 の修復。制約を満たす移動しか行わない。"""
import pytest

from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.objectives import Weights, measure
from app.scheduler.repair import EFFORT_SECONDS, repair
from tests.factories import subject as make


def build(subjects, teachers=()):
    return Context.from_lists(subjects, list(teachers))


def test_all_sliders_off_changes_nothing():
    """従来どおりの結果になること。既定はこの状態。"""
    subjects = [make("A1"), make("A2", teacher="教員乙")]
    ctx = build(subjects)
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.SOLVER)
    tt.place("A2", (TimeSlot("月", 5),), AssignmentSource.SOLVER)

    before = {c: tt.slot_of(c) for c in ("A1", "A2")}
    repair(ctx, tt, Weights.from_steps({k: "off" for k in (
        "student_gaps", "student_days", "teacher_gaps",
        "early_periods", "seminar_adjacency")}), seconds=5)
    assert {c: tt.slot_of(c) for c in ("A1", "A2")} == before


def test_a_student_gap_gets_closed():
    """1 限と 4 限だけの日は、間を詰める。"""
    subjects = [make(f"A{n}", teacher=f"教員{n}") for n in (1, 2)]
    ctx = build(subjects)
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.SOLVER)
    tt.place("A2", (TimeSlot("月", 4),), AssignmentSource.SOLVER)
    assert measure(ctx, tt).student_gaps == 2

    repair(ctx, tt, Weights(student_gaps=1.0, early_periods=0.0), seconds=5)
    assert measure(ctx, tt).student_gaps == 0


def test_repair_never_leaves_a_violation():
    subjects = [make(f"A{n}", teacher="同じ先生") for n in (1, 2, 3)]
    ctx = build(subjects, [Teacher("同じ先生", TeacherKind.FULL_TIME)])
    tt = Timetable()
    for n, period in ((1, 1), (2, 3), (3, 5)):
        tt.place(f"A{n}", (TimeSlot("月", period),), AssignmentSource.SOLVER)

    repair(ctx, tt, Weights(student_gaps=1.0), seconds=5)
    assert validate_all(ctx, tt) == []


def test_repair_never_unplaces_anything():
    subjects = [make(f"A{n}", teacher=f"教員{n}") for n in range(1, 6)]
    ctx = build(subjects)
    tt = Timetable()
    for n in range(1, 6):
        tt.place(f"A{n}", (TimeSlot("月", n),), AssignmentSource.SOLVER)

    repair(ctx, tt, Weights(student_gaps=1.0, student_days=1.0), seconds=5)
    assert len(tt.assignments) == 5


def test_a_slot_the_office_fixed_is_left_alone():
    """Excel や編成規則で決まった枠は動かさない。"""
    fixed = make("A1", teacher="教員甲", fixed_slot=(TimeSlot("水", 1),))
    other = make("A2", teacher="教員乙")
    ctx = build([fixed, other])
    tt = Timetable()
    tt.place("A1", (TimeSlot("水", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("水", 4),), AssignmentSource.SOLVER)

    repair(ctx, tt, Weights(student_gaps=1.0), seconds=5)
    assert tt.slot_of("A1") == (TimeSlot("水", 1),)


def test_the_time_limit_is_honoured():
    subjects = [make(f"A{n}", teacher=f"教員{n}") for n in range(1, 30)]
    ctx = build(subjects)
    tt = Timetable()
    for n, subject in enumerate(subjects, start=1):
        tt.place(subject.code, (TimeSlot("月火水木金"[n % 5], n % 5 + 1),),
                 AssignmentSource.SOLVER)

    import time
    started = time.monotonic()
    repair(ctx, tt, Weights(student_gaps=1.0, student_days=1.0), seconds=0.2)
    assert time.monotonic() - started < 5


@pytest.mark.parametrize("effort,seconds", [("off", 0.0), ("short", 5.0), ("long", 60.0)])
def test_the_effort_steps_map_to_seconds(effort, seconds):
    assert EFFORT_SECONDS[effort] == seconds


def test_repair_keeps_the_source_that_placed_a_subject():
    """動かしても「誰が決めたコマか」は変わらない。

    画面のレール色は配置元を表す唯一の手掛かりなので、修復が
    ソルバー扱いに書き換えると事務局には嘘が見える。
    """
    ctx = build([make("A1", teacher="教員甲")])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 5),), AssignmentSource.PRELOCK)

    repair(ctx, tt, Weights(early_periods=1.0), seconds=5)

    assert tt.slot_of("A1") != (TimeSlot("月", 5),), "5 限から動くはずの場面"
    assert tt.assignments["A1"].source is AssignmentSource.PRELOCK


def test_an_inherited_placement_is_left_where_last_year_put_it():
    """踏襲モードは前年度のコマに**ロックする**と決めてある。

    修復が黙って動かすと、事務局が確認しなくてよいはずの科目まで
    去年と違う場所に現れる。
    """
    ctx = build([make("A1", teacher="教員甲")])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 5),), AssignmentSource.INHERITED)

    repair(ctx, tt, Weights(early_periods=1.0), seconds=5)

    assert tt.slot_of("A1") == (TimeSlot("月", 5),)
