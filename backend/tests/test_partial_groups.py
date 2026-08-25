"""AI が「同じコマに入るべき科目」の片方だけを置いた場合の後始末。

H4（合同）と H12（前後期）は同一コマを要求する。片方が先に置かれると
残りはそのコマ以外を選べず、そこが埋まっていれば永久に置けない。
ソルバーは自分でグループごと置くとき先読みするが、Gemini が片方だけ
置いて残りを未確定にした場合は手遅れになる。
"""
from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.models.enums import Category, Department, Term
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.pipeline import release_partial_groups
from app.scheduler.solver import solve
from tests.factories import subject as make


def test_a_half_placed_joint_pair_is_released():
    """実例：合同の経営側を AI が金 1 に置いたが、会計側は朝学習で
    金 1 に置けなかった（A56301 / B56301）。"""
    management = make("B1", joint_id="J1", teacher="教員甲")
    accounting = make("A1", joint_id="J1", teacher="教員甲",
                      department=Department.ACCOUNTING)
    ctx = Context.from_lists([management, accounting], [])
    tt = Timetable()
    tt.place("B1", (TimeSlot("金", 1),), AssignmentSource.GEMINI)

    released = release_partial_groups(ctx, tt, ["A1"])
    assert released == ["B1"]
    assert not tt.is_placed("B1")


def test_a_group_that_is_fully_placed_is_left_alone():
    management = make("B1", joint_id="J1", teacher="教員甲")
    accounting = make("A1", joint_id="J1", teacher="教員甲",
                      department=Department.ACCOUNTING)
    ctx = Context.from_lists([management, accounting], [])
    tt = Timetable()
    for code in ("B1", "A1"):
        tt.place(code, (TimeSlot("金", 1),), AssignmentSource.GEMINI)

    assert release_partial_groups(ctx, tt, []) == []
    assert tt.is_placed("B1") and tt.is_placed("A1")


def test_a_group_the_office_fixed_is_left_alone():
    """Excel や編成規則で決まった枠は外さない。"""
    fixed = make("B1", joint_id="J1", teacher="教員甲",
                 fixed_slot=(TimeSlot("水", 1),))
    partner = make("A1", joint_id="J1", teacher="教員甲",
                   department=Department.ACCOUNTING)
    ctx = Context.from_lists([fixed, partner], [])
    tt = Timetable()
    tt.place("B1", (TimeSlot("水", 1),), AssignmentSource.PRELOCK)

    assert release_partial_groups(ctx, tt, ["A1"]) == []
    assert tt.is_placed("B1")


def _blocked_everywhere_except(ctx, tt, keep, term, year, department):
    """keep 以外の全コマを、同じ学科・年次の必修で塞ぐ。"""
    for day in "月火水木金":
        for period in range(1, 6):
            slot = TimeSlot(day, period)
            if slot == keep:
                continue
            code = f"F{day}{period}{term.value}{year}"
            ctx.subjects[code] = make(
                code, department=department, year=year, term=term,
                teacher=f"埋{code}", category=Category.REQUIRED)
            tt.place(code, (slot,), AssignmentSource.PRELOCK)


def test_releasing_lets_the_solver_place_the_whole_group():
    """外したあと、全員が入れるコマへソルバーが置き直せること。"""
    spring = make("S1", pair_id="P1", term=Term.SPRING, teacher="教員甲")
    fall = make("F1", pair_id="P1", term=Term.FALL, teacher="教員甲")
    ctx = Context.from_lists([spring, fall], [])
    tt = Timetable()
    # AI は前期を月1 に置いた。しかし後期の月1 は別の必修で埋まっている
    tt.place("S1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    blocker = make("BLOCK", term=Term.FALL, teacher="別の教員")
    ctx.subjects["BLOCK"] = blocker
    tt.place("BLOCK", (TimeSlot("月", 1),), AssignmentSource.GEMINI)

    # そのままソルバーへ渡すと後期は置けない
    plain = Timetable()
    plain.place("S1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    plain.place("BLOCK", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    assert solve(ctx, plain, ["F1"]) == ["F1"]

    # 外してから渡すと、両方が入るコマへ置き直される
    released = release_partial_groups(ctx, tt, ["F1"])
    assert released == ["S1"]
    assert solve(ctx, tt, sorted({"F1", *released})) == []
    assert tt.slot_of("S1") == tt.slot_of("F1")
    assert tt.slot_of("S1") != (TimeSlot("月", 1),)
    assert validate_all(ctx, tt) == []


def test_the_pipeline_recovers_from_a_half_placed_group(tmp_path):
    """AI が片方だけ置いた状態でパイプラインを回しても未配置にならない。"""
    from app.logging.session_logger import SessionLogger
    from app.models.subject import Subject
    from app.scheduler.pipeline import GenerationMode, run_pipeline

    def build(code, **kwargs):
        return make(code, teacher="教員甲", **kwargs)

    spring = build("S1", pair_id="P1", term=Term.SPRING)
    fall = build("F1", pair_id="P1", term=Term.FALL)
    blocker = make("BLOCK", term=Term.FALL, teacher="別の教員")
    subjects = [spring, fall, blocker]

    def placer(context, timetable, codes, logger):
        """前期と邪魔者だけを置き、後期を未確定のまま返す AI の代役。"""
        for code, slot in (("S1", TimeSlot("月", 1)), ("BLOCK", TimeSlot("月", 1))):
            if code in codes and not timetable.is_placed(code):
                timetable.place(code, (slot,), AssignmentSource.GEMINI)
        return [c for c in codes if not timetable.is_placed(c)]

    logger = SessionLogger("partial", log_dir=tmp_path)
    result = run_pipeline(subjects, {}, GenerationMode.OPTIMIZE, logger,
                          gemini_placer=placer)
    logger.close()

    assert result.unplaced == []
    assert result.violations == []
    timetable = result.timetable
    assert timetable.slot_of("S1") == timetable.slot_of("F1")
