"""学科ごとの編成規則（朝学習・曜日固定）と、その例外。"""
import json

import pytest

from app.constraints.context import Context
from app.constraints.subject_rules import check_h13
from app.constraints.teacher_rules import check_h7
from app.ingest.department_rules import load_department_rules
from app.models.enums import Department, TeacherKind, Term
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from tests.factories import subject as make

CONFIG = {
    "morning_study": [
        {"department": "会計", "year": 1, "days": ["月", "火", "木", "金"], "period": 1}
    ],
    "fixed_days": [
        {
            "department": "会計", "year": 1, "day": "水",
            "periods": {"1": ["商業簿記Ⅰ"], "4": ["工業簿記演習Ⅰ"]},
            "ignore_consecutive_limit": True,
        }
    ],
}


@pytest.fixture(autouse=True)
def rules(tmp_path, monkeypatch):
    path = tmp_path / "department_rules.json"
    path.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    loaded = load_department_rules(path)
    for module in ("app.constraints.subject_rules", "app.constraints.teacher_rules",
                   "app.ingest.validators"):
        monkeypatch.setattr(f"{module}.RULES", loaded)
    return loaded


def accounting(code, **kwargs):
    return make(code, department=Department.ACCOUNTING, **kwargs)


def test_morning_study_keeps_the_first_period_free():
    subject = accounting("A1")
    ctx = Context.from_lists([subject], [])
    for day in ("月", "火", "木", "金"):
        violations = check_h13(ctx, Timetable(), subject, (TimeSlot(day, 1),))
        assert [v.rule_id for v in violations] == ["H13"], day


def test_wednesday_has_no_morning_study():
    """水曜だけは 1 限から 4 限まで事務局が編成を決めている。"""
    subject = accounting("A1")
    ctx = Context.from_lists([subject], [])
    assert check_h13(ctx, Timetable(), subject, (TimeSlot("水", 1),)) == []


def test_later_periods_are_untouched():
    subject = accounting("A1")
    ctx = Context.from_lists([subject], [])
    assert check_h13(ctx, Timetable(), subject, (TimeSlot("月", 2),)) == []


def test_other_departments_and_years_keep_their_first_period():
    ctx = Context.from_lists([], [])
    for subject in (make("B1"), accounting("A2", year=2)):
        assert check_h13(ctx, Timetable(), subject, (TimeSlot("月", 1),)) == []


def test_availability_outranks_morning_study():
    """出勤可能コマがすべて朝学習に重なるなら、朝学習が譲る。

    非常勤が来られるかどうかは動かしようがない。実データでは金 1 限しか
    出勤できない先生の科目が、金 1 が朝学習になって行き場を失った。
    """
    subject = accounting("A1", teacher="金曜だけ先生")
    teacher = Teacher("金曜だけ先生", TeacherKind.PART_TIME,
                      available_slots={TimeSlot("金", 1)})
    ctx = Context.from_lists([subject], [teacher])
    assert check_h13(ctx, Timetable(), subject, (TimeSlot("金", 1),)) == []


def test_morning_study_holds_when_the_teacher_has_somewhere_else_to_go():
    subject = accounting("A1", teacher="余裕のある先生")
    teacher = Teacher("余裕のある先生", TeacherKind.PART_TIME,
                      available_slots={TimeSlot("金", 1), TimeSlot("金", 2)})
    ctx = Context.from_lists([subject], [teacher])
    assert [v.rule_id for v in check_h13(ctx, Timetable(), subject, (TimeSlot("金", 1),))] == ["H13"]


def test_a_full_time_teacher_gets_no_exception():
    subject = accounting("A1", teacher="専任先生")
    ctx = Context.from_lists([subject], [Teacher("専任先生", TeacherKind.FULL_TIME)])
    assert [v.rule_id for v in check_h13(ctx, Timetable(), subject, (TimeSlot("金", 1),))] == ["H13"]


def test_the_fixed_wednesday_does_not_count_towards_the_consecutive_limit():
    """簿記は 1 限から 4 限まで続くと決まっている。担当はそこで必ず
    4 連続するので、その 4 コマを連続の数に入れない。"""
    first = accounting("A1", base_name="商業簿記Ⅰ", teacher="簿記先生")
    fourth = accounting("A4", base_name="工業簿記演習Ⅰ", teacher="簿記先生")
    ctx = Context.from_lists([first, fourth], [Teacher("簿記先生", TeacherKind.PART_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("水", 1),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, fourth, (TimeSlot("水", 4),)) == []


def test_the_same_teacher_s_other_classes_still_count():
    """「無視してよい」を教員まるごとに広げない。

    固定枠の水 1 限は数えないが、水 2〜5 限に別の授業を入れれば、
    それは通常どおり 4 コマ連続として弾かれる。
    """
    fixed = accounting("A1", base_name="商業簿記Ⅰ", teacher="簿記先生")
    others = [accounting(f"X{n}", teacher="簿記先生") for n in (2, 3, 4, 5)]
    ctx = Context.from_lists([fixed, *others], [Teacher("簿記先生", TeacherKind.PART_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("水", 1),), AssignmentSource.PRELOCK)
    for code, period in (("X2", 2), ("X3", 3), ("X4", 4)):
        tt.place(code, (TimeSlot("水", period),), AssignmentSource.SOLVER)
    violations = check_h7(ctx, tt, ctx.subjects["X5"], (TimeSlot("水", 5),))
    assert [v.rule_id for v in violations] == ["H7"]


def test_the_fixed_slot_alone_never_trips_the_limit():
    """固定枠だけで 4 連続しても弾かれない。実データの簿記 4 コマがこれ。"""
    fixed = [accounting("A1", base_name="商業簿記Ⅰ", teacher="簿記先生"),
             accounting("A4", base_name="工業簿記演習Ⅰ", teacher="簿記先生")]
    middle = [accounting(f"M{n}", teacher="簿記先生") for n in (2, 3)]
    ctx = Context.from_lists([*fixed, *middle], [Teacher("簿記先生", TeacherKind.PART_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("水", 1),), AssignmentSource.PRELOCK)
    for code, period in (("M2", 2), ("M3", 3)):
        tt.place(code, (TimeSlot("水", period),), AssignmentSource.SOLVER)
    # 数えるのは M2・M3 の 2 コマだけなので、固定枠の水 4 限は通る
    assert check_h7(ctx, tt, ctx.subjects["A4"], (TimeSlot("水", 4),)) == []


def test_a_missing_config_disables_the_rules(tmp_path):
    rules = load_department_rules(tmp_path / "absent.json")
    assert rules.morning_study == [] and rules.fixed_days == []


def test_a_retake_class_is_not_bound_by_the_morning_study_hour():
    """朝学習は 1 年生の運用。【再】を履修するのは 2 年生以降なので掛からない。

    実データの 会計1年【再】13 件が、この規則で月火木金の 1 限から
    締め出されていた。前年度は 日本語リテラシーⅠ【再】:会 を 月1 に置いている。
    """
    subject = accounting("A1", name="日本語リテラシーⅠ【再】:会",
                         base_name="日本語リテラシーⅠ")
    ctx = Context.from_lists([subject], [])
    for day in ("月", "火", "木", "金"):
        assert check_h13(ctx, Timetable(), subject, (TimeSlot(day, 1),)) == [], day


def test_a_regular_class_is_still_bound_by_the_morning_study_hour():
    """緩めすぎていないことの網。【再】でなければ従来どおり掛かる。"""
    subject = accounting("A2", name="日本語リテラシーⅠ:会", base_name="日本語リテラシーⅠ")
    ctx = Context.from_lists([subject], [])
    assert [v.rule_id for v in
            check_h13(ctx, Timetable(), subject, (TimeSlot("月", 1),))] == ["H13"]


def test_the_wednesday_block_still_pins_the_retake_classes():
    """水曜の枠は事務局が科目名で明示指定したもの。【再】も含めたまま。

    base_name で突合するので、通常クラスと【再】クラスが同じコマに入る。
    朝学習と違い、これは意図した運用なので変えない。
    """
    from app.ingest.curriculum_reader import _fixed_slot

    slot = _fixed_slot(None, Department.ACCOUNTING, 1, "商業簿記Ⅰ", 1)
    assert slot == (TimeSlot("水", 1),)
