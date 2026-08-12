from app.constraints.validator import validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource
from app.logging.session_logger import SessionLogger
from app.scheduler.pipeline import GenerationMode, run_pipeline


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=f"教員{code}",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_mock_mode_places_everything_with_solver(tmp_path):
    subjects = [make(f"A{i}") for i in range(5)]
    logger = SessionLogger("t1", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.unplaced == []
    assert result.violations == []
    assert len(result.timetable.placed_codes()) == 5
    assert all(
        a.source is AssignmentSource.SOLVER for a in result.timetable.assignments.values()
    )
    logger.close()


def test_intensive_subjects_are_excluded_from_grid(tmp_path):
    subjects = [make("A1"), make("A2", is_intensive=True)]
    logger = SessionLogger("t2", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.intensive_codes == ["A2"]
    assert result.timetable.placed_codes() == {"A1"}
    logger.close()


def test_fixed_slot_subject_keeps_prelock_source(tmp_path):
    subjects = [make("A1", fixed_slot=(TimeSlot("火", 3),))]
    logger = SessionLogger("t3", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.timetable.slot_of("A1") == (TimeSlot("火", 3),)
    assert result.timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    logger.close()


def test_warnings_are_collected_but_do_not_stop_generation(tmp_path):
    subjects = [make("A1", teacher="未登録教員")]
    logger = SessionLogger("t4", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert [w.kind for w in result.warnings] == ["unknown_teacher"]
    assert result.timetable.is_placed("A1")
    logger.close()


def test_optimize_mode_uses_gemini_placer_then_solver(tmp_path):
    subjects = [make("A1"), make("A2")]
    calls = []

    def fake_placer(context, timetable, codes, logger):
        calls.append(list(codes))
        timetable.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
        return ["A2"]  # A2 は収束しなかったことにする

    logger = SessionLogger("t5", log_dir=tmp_path)
    result = run_pipeline(
        subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=fake_placer
    )

    assert calls  # Gemini 段階が呼ばれた
    assert result.timetable.assignments["A1"].source is AssignmentSource.GEMINI
    assert result.timetable.assignments["A2"].source is AssignmentSource.SOLVER
    assert result.unplaced == []
    logger.close()


def test_gemini_placer_is_called_by_category_in_order(tmp_path):
    subjects = [
        make("E1", category=Category.ELECTIVE),
        make("R1", category=Category.REQUIRED),
        make("S1", category=Category.ELECTIVE_REQUIRED, courses=["情報コース"]),
    ]
    seen = []

    def fake_placer(context, timetable, codes, logger):
        seen.append(sorted(codes))
        return list(codes)

    logger = SessionLogger("t6", log_dir=tmp_path)
    run_pipeline(subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=fake_placer)

    assert seen == [["R1"], ["S1"], ["E1"]]
    logger.close()


def test_falls_back_to_solver_when_gemini_places_nothing(tmp_path):
    subjects = [make("A1"), make("A2")]

    def failing_placer(context, timetable, codes, logger):
        return list(codes)

    logger = SessionLogger("t7", log_dir=tmp_path)
    result = run_pipeline(
        subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=failing_placer
    )

    assert len(result.timetable.placed_codes()) == 2
    assert result.violations == []
    logger.close()


def test_logger_records_each_stage(tmp_path):
    logger = SessionLogger("t8", log_dir=tmp_path)
    run_pipeline([make("A1")], [], GenerationMode.MOCK, logger)
    stages = {e.stage for e in logger.events}
    assert {"Stage 0", "Stage 1", "Stage 5", "Stage 6"} <= stages
    logger.close()


def test_part_time_subject_is_prelocked(tmp_path):
    subjects = [make("A1", teacher="非常勤甲")]
    teachers = [Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 2)})]
    logger = SessionLogger("t9", log_dir=tmp_path)
    result = run_pipeline(subjects, teachers, GenerationMode.MOCK, logger)

    assert result.timetable.slot_of("A1") == (TimeSlot("金", 2),)
    assert result.timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    logger.close()
