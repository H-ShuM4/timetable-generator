from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum, to_base_name
from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot

CURRICULUM_XLSX = Path(__file__).resolve().parents[2] / "カリキュラム一覧(整形済み).xlsx"


def test_to_base_name_strips_accounting_suffix():
    assert to_base_name("日本語リテラシーⅠ:会") == "日本語リテラシーⅠ"


def test_to_base_name_strips_retake_marker():
    assert to_base_name("日本語リテラシーⅠ【再】:会") == "日本語リテラシーⅠ"


def test_to_base_name_strips_double_slot_marker():
    assert to_base_name("▲デジタル画像編集（Photoshop）") == "デジタル画像編集（Photoshop）"


def test_to_base_name_leaves_plain_name_untouched():
    assert to_base_name("経営情報管理") == "経営情報管理"


def _by_code(subjects):
    return {s.code: s for s in subjects}


def test_reads_real_workbook_and_merges_double_slot_rows():
    subjects = read_curriculum(CURRICULUM_XLSX)
    # 大学 496 行 + 短大 166 行 = 662 行。▲科目 4 件が各 2 行 → 4 件減る
    assert len(subjects) == 658
    assert len({s.code for s in subjects}) == len(subjects)


def test_double_slot_subject_requires_two_consecutive_slots():
    photoshop = _by_code(read_curriculum(CURRICULUM_XLSX))["J15901"]
    assert photoshop.slots_required == 2
    assert photoshop.requires_consecutive is True
    assert photoshop.base_name == "デジタル画像編集（Photoshop）"
    assert photoshop.quarter is Quarter.Q2


def test_pre_seminar_is_the_non_consecutive_exception():
    pre_seminar = _by_code(read_curriculum(CURRICULUM_XLSX))["J10405"]
    assert pre_seminar.slots_required == 2
    assert pre_seminar.requires_consecutive is False
    assert pre_seminar.is_seminar is True
    # 事務局が曜日・時限を空にしたため確定枠は無く、システムが配置する
    assert pre_seminar.fixed_slot is None


def test_intensive_subject_has_no_fixed_slot():
    subjects = read_curriculum(CURRICULUM_XLSX)
    intensives = [s for s in subjects if s.is_intensive]
    assert len(intensives) == 45  # 大学 26 + 短大 19
    assert all(s.fixed_slot is None for s in intensives)


def test_retake_subject_shares_base_name_with_original():
    subjects = _by_code(read_curriculum(CURRICULUM_XLSX))
    assert subjects["A50201"].base_name == "日本語リテラシーⅠ"
    assert subjects["A50206"].base_name == "日本語リテラシーⅠ"
    assert subjects["A50206"].is_seminar is True


def test_university_courses_are_read_including_multi_course_subjects():
    subjects = read_curriculum(CURRICULUM_XLSX)
    management = {
        course for s in subjects
        if s.department is Department.MANAGEMENT for course in s.courses
    }
    assert {"経営", "情報", "観光まちづくり"} <= management

    # 複数コース所属は全角読点区切りで書かれている
    multi = [s for s in subjects if len(s.courses) > 1]
    assert multi
    assert all(len(s.courses) == len(set(s.courses)) for s in multi)


def test_junior_courses_are_read_from_the_field_column():
    subjects = read_curriculum(CURRICULUM_XLSX)
    junior = {
        course for s in subjects
        if s.department is Department.JUNIOR for course in s.courses
    }
    assert {"経営", "情報デザイン", "グローバルコミュニケーション"} <= junior


def test_every_elective_required_subject_has_a_course():
    subjects = read_curriculum(CURRICULUM_XLSX)
    elective_required = [s for s in subjects if s.category is Category.ELECTIVE_REQUIRED]
    assert len(elective_required) == 102  # 経営58 + 短大44
    assert all(s.courses for s in elective_required)


def test_accounting_has_no_courses_by_design():
    subjects = read_curriculum(CURRICULUM_XLSX)
    accounting = [s for s in subjects if s.department is Department.ACCOUNTING]
    assert accounting
    assert all(s.courses == [] for s in accounting)
    assert not [s for s in accounting if s.category is Category.ELECTIVE_REQUIRED]


def test_junior_remote_flag_is_read():
    subjects = read_curriculum(CURRICULUM_XLSX)
    remote = [s for s in subjects if s.department is Department.JUNIOR and s.is_remote]
    assert len(remote) == 13


def test_department_and_category_are_parsed():
    subjects = _by_code(read_curriculum(CURRICULUM_XLSX))
    academic = subjects["A50101"]
    assert academic.department is Department.ACCOUNTING
    assert academic.category is Category.REQUIRED
    assert academic.term is Term.FALL
    assert academic.fixed_slot == (TimeSlot("火", 3),)
