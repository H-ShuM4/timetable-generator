from app.constraints.context import Context
from app.logging.session_logger import SessionLogger
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.inherit import (
    InheritPlan,
    PreviousEntry,
    apply_plan,
    detect_retarget_codes,
)


def make(code, teacher="専任甲", **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=teacher,
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_part_time_and_special_teachers_are_always_retargeted():
    subjects = [make("A1", teacher="非常勤甲"), make("A2", teacher="特任甲")]
    teachers = {
        "非常勤甲": Teacher("非常勤甲", TeacherKind.PART_TIME),
        "特任甲": Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水"}),
    }
    previous = {
        "A1": PreviousEntry((TimeSlot("月", 1),), "非常勤甲"),
        "A2": PreviousEntry((TimeSlot("水", 1),), "特任甲"),
    }
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == {"A1", "A2"}


def test_changed_research_day_is_retargeted():
    subjects = [make("A1", teacher="専任甲")]
    current = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="水")}
    previous_teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, current, previous, previous_teachers) == {"A1"}


def test_unchanged_full_time_teacher_is_not_retargeted():
    subjects = [make("A1", teacher="専任甲")]
    teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == set()


def test_new_subject_is_retargeted():
    subjects = [make("A9", teacher="専任甲")]
    teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    assert detect_retarget_codes(subjects, teachers, {}, teachers) == {"A9"}


def test_changed_teacher_is_retargeted():
    subjects = [make("A1", teacher="専任乙")]
    teachers = {
        "専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火"),
        "専任乙": Teacher("専任乙", TeacherKind.FULL_TIME, research_day="火"),
    }
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == {"A1"}


def test_apply_plan_places_non_retargeted_subjects(tmp_path):
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i1", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.slot_of("A1") == (TimeSlot("木", 4),)
    assert tt.assignments["A1"].source is AssignmentSource.INHERITED
    logger.close()


def test_apply_plan_skips_retargeted_subjects(tmp_path):
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, {"A1"})
    logger = SessionLogger("i2", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    logger.close()


def test_apply_plan_skips_when_previous_slot_now_violates(tmp_path):
    # 前年度は木曜だったが、今年度は研究日が木曜に変わった
    subject = make("A1", teacher="専任甲")
    teachers = [Teacher("専任甲", TeacherKind.FULL_TIME, research_day="木")]
    ctx = Context.from_lists([subject], teachers)
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i3", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    assert any(e.level == "WARN" for e in logger.events)
    logger.close()


def test_apply_plan_ignores_codes_absent_from_this_year(tmp_path):
    ctx = Context.from_lists([], [])
    tt = Timetable()
    plan = InheritPlan({"Z9": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i4", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    logger.close()


def test_apply_plan_leaves_a_subject_that_became_intensive_off_the_grid(tmp_path):
    """今年度は集中講義になった科目を、前年度の枠へ戻さない。

    実データで起きた：J19901 模擬ブライダルプロジェクトは今年度 時限99
    （集中）だが前年度は 水5 に入っており、踏襲がグリッドへ載せていた。
    集中講義は別枠の一覧にも出るため、同じ科目が 2 か所に現れる。
    """
    subject = make("A1", is_intensive=True)
    context = Context.from_lists([subject], [])
    timetable = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("水", 5),), "専任甲")}, set())

    logger = SessionLogger("intensive", log_dir=tmp_path)
    apply_plan(context, timetable, plan, logger)
    logger.close()

    assert timetable.is_placed("A1") is False
