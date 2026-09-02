from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum, to_base_name
from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot

from tests.conftest import CURRICULUM_XLSX  # noqa: E402


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


def test_remote_column_distinguishes_maru_batsu_and_blank():
    """遠隔列は ○ / × / 空欄 の 3 状態。× は ○ の否定ではない。"""
    subjects = read_curriculum(CURRICULUM_XLSX)
    yes = [s for s in subjects if s.is_remote]
    no = [s for s in subjects if s.is_remote_prohibited]
    blank = [s for s in subjects if not s.is_remote and not s.is_remote_prohibited]

    assert not [s for s in subjects if s.is_remote and s.is_remote_prohibited]
    # 大学シートは全行が ○ か ×、短大シートは ○ か空欄
    assert all(s.department is not Department.JUNIOR for s in no)
    assert all(s.department is Department.JUNIOR for s in blank)
    # 件数そのものは事務局が Excel を更新するたびに動くので固定しない
    # （実際 ○ が 89→88 に変わってこのテストが落ちた）。守るのは 3 状態が
    # 混ざらないことと、どの状態も実データに存在することである。
    assert yes and no and blank
    assert len(yes) + len(no) + len(blank) == len(subjects)
    assert any(s.department is Department.JUNIOR for s in yes), "短大にも ○ がある"


def test_the_accounting_wednesday_is_fixed_from_the_department_rules():
    """事務局が決めた水曜の編成。Excel には書かれていない。"""
    subjects = {s.code: s for s in read_curriculum(CURRICULUM_XLSX)}
    expected = {
        "商業簿記Ⅰ": 1, "商業簿記Ⅱ": 1,
        "商業簿記演習Ⅰ": 2, "商業簿記演習Ⅱ": 2,
        "工業簿記Ⅰ": 3, "工業簿記Ⅱ": 3,
        "工業簿記演習Ⅰ": 4, "工業簿記演習Ⅱ": 4,
    }
    same_name = [s for s in subjects.values() if s.base_name in expected and s.year == 1]
    fixed = [s for s in same_name if s.department is Department.ACCOUNTING]
    # 8 科目名 × 通常と【再】の 2 クラス
    assert len(fixed) == 16
    for subject in fixed:
        assert subject.fixed_slot is not None, subject.code
        slot = subject.fixed_slot[0]
        assert (slot.day, slot.period) == ("水", expected[subject.base_name]), subject.code

    # 経営 1 年と短大 1 年にも同名の科目がある。規則は会計 1 年だけに効く
    others = [s for s in same_name if s.department is not Department.ACCOUNTING]
    assert others, "他学科に同名の科目が無いと、この絞り込みを検証できない"
    assert all(s.fixed_slot is None for s in others), [s.code for s in others]


def test_class_markers_are_stripped_for_the_student_conflict_check():
    """英語Ⅰ【A】と英語Ⅰ【B】は 1 科目の複数クラス。

    base_name はクラス記号を残す（合同ペアリングが経営の【A】と会計の
    【A】を組にするため）。学生側の衝突判定だけが class_group を見る。
    """
    subjects = read_curriculum(CURRICULUM_XLSX)
    english = [s for s in subjects if s.base_name.startswith("英語Ⅰ【")]
    assert english, "クラス記号付きの英語Ⅰが実データに無い"
    assert {s.class_group for s in english} == {"英語Ⅰ"}
    assert len({s.base_name for s in english}) > 1, "base_name は分かれたまま"


def test_a_multi_character_bracket_is_not_a_class_marker():
    """【留学生】は履修する集団が違うのであって、クラス分けではない。"""
    subjects = read_curriculum(CURRICULUM_XLSX)
    foreign = [s for s in subjects if "【留学生】" in s.name]
    assert foreign, "【留学生】が実データに無い"
    for subject in foreign:
        assert "【留学生】" in subject.class_group


def test_a_retake_class_is_flagged_and_shares_the_subject_name():
    subjects = read_curriculum(CURRICULUM_XLSX)
    retake = [s for s in subjects if s.is_retake]
    assert len(retake) == 19
    assert all("【再】" in s.name for s in retake)

    literacy = next(s for s in retake if s.name.startswith("日本語リテラシーⅠ【再】"))
    assert literacy.class_group == "日本語リテラシーⅠ"
    assert literacy.year == 1, "配当年次は 1 年のまま（受けるのは 2 年生以降）"


def test_a_regular_class_is_not_flagged_as_a_retake():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assert not any(s.is_retake for s in subjects if "【再】" not in s.name)
