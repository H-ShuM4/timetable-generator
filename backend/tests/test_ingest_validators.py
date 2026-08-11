from app.ingest.validators import Warning, collect_warnings
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot


def _subject(code="A1", category=Category.REQUIRED, teacher="教員甲", courses=None):
    return Subject(
        code=code,
        name="科目",
        base_name="科目",
        department=Department.MANAGEMENT,
        year=1,
        term=Term.SPRING,
        quarter=None,
        category=category,
        courses=courses or [],
        teacher=teacher,
    )


def _kinds(warnings):
    return sorted({w.kind for w in warnings})


def test_unknown_teacher_is_reported():
    warnings = collect_warnings([_subject(teacher="未登録教員")], {}, [])
    assert _kinds(warnings) == ["unknown_teacher"]
    assert warnings[0].teacher_name == "未登録教員"


def test_part_time_without_availability_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.PART_TIME)}
    warnings = collect_warnings([_subject()], teachers, [])
    assert _kinds(warnings) == ["missing_availability"]


def test_part_time_with_availability_is_clean():
    teachers = {
        "教員甲": Teacher("教員甲", TeacherKind.PART_TIME, available_slots={TimeSlot("月", 1)})
    }
    assert collect_warnings([_subject()], teachers, []) == []


def test_full_time_without_availability_is_clean():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME, research_day="火")}
    assert collect_warnings([_subject()], teachers, []) == []


def test_joint_flag_mismatch_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    warnings = collect_warnings([_subject(code="A9")], teachers, ["A9"])
    assert _kinds(warnings) == ["joint_flag_mismatch"]
    assert warnings[0].subject_code == "A9"


def test_elective_required_without_course_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    subject = _subject(category=Category.ELECTIVE_REQUIRED, courses=[])
    assert _kinds(collect_warnings([subject], teachers, [])) == ["missing_course"]


def test_elective_required_with_course_is_clean():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    subject = _subject(category=Category.ELECTIVE_REQUIRED, courses=["情報コース"])
    assert collect_warnings([subject], teachers, []) == []


def test_warning_is_hashable_and_comparable():
    a = Warning("unknown_teacher", "教員が見つかりません", None, "教員甲")
    b = Warning("unknown_teacher", "教員が見つかりません", None, "教員甲")
    assert a == b


def test_partial_slot_is_reported_by_reader_level_check():
    from app.ingest.validators import check_partial_slots

    rows = [
        {"授業コード": "A1", "曜日": "月", "時限": None},
        {"授業コード": "A2", "曜日": None, "時限": 3},
        {"授業コード": "A3", "曜日": "火", "時限": 2},
        {"授業コード": "A4", "曜日": None, "時限": None},
    ]
    warnings = check_partial_slots(rows)
    assert [w.subject_code for w in warnings] == ["A1", "A2"]
    assert all(w.kind == "partial_slot" for w in warnings)
