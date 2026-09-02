from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum
from app.ingest.joint_pairing import assign_joint_ids
from app.models.enums import Category, Department, Term
from app.models.subject import Subject

from tests.conftest import CURRICULUM_XLSX  # noqa: E402


def _subject(code, base_name, department, term, teacher, is_joint=True):
    return Subject(
        code=code,
        name=base_name,
        base_name=base_name,
        department=department,
        year=2,
        term=term,
        quarter=None,
        category=Category.ELECTIVE,
        teacher=teacher,
        is_joint=is_joint,
    )


def test_matching_pair_gets_same_joint_id():
    subjects = [
        _subject("A1", "経営情報管理", Department.ACCOUNTING, Term.SPRING, "荒牧裕一"),
        _subject("B1", "経営情報管理", Department.MANAGEMENT, Term.SPRING, "荒牧裕一"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is not None
    assert subjects[0].joint_id == subjects[1].joint_id


def test_different_term_does_not_pair_and_is_not_reported():
    # マーケティングプロジェクトは会計1年前期・経営1年後期。別の授業なので正常
    subjects = [
        _subject("A2", "マーケティングプロジェクト", Department.ACCOUNTING, Term.SPRING, "増渕賢一郎"),
        _subject("B2", "マーケティングプロジェクト", Department.MANAGEMENT, Term.FALL, "増渕賢一郎"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None
    assert subjects[1].joint_id is None


def test_lone_joint_subject_is_normal():
    # その教員のコマが片方の学科にしかないゼミ。相手がいないので単独のまま
    subjects = [
        _subject("A3", "卒業研究Ⅰ", Department.ACCOUNTING, Term.SPRING, "神山直規"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_flag_mismatch_is_reported():
    # 同じ科目・教員・開講期なのに会計側だけフラグが無い＝付け忘れ
    subjects = [
        _subject("B4", "アート表現", Department.MANAGEMENT, Term.FALL, "前沢知子"),
        _subject("A4", "アート表現", Department.ACCOUNTING, Term.FALL, "前沢知子", is_joint=False),
    ]
    assert assign_joint_ids(subjects) == ["A4"]
    assert subjects[0].joint_id is None


def test_extra_section_in_the_same_department_is_not_a_mismatch():
    # 育児と介護は経営に2クラスあり、B2 のみ会計と合同。B1 は単独クラスで正常
    subjects = [
        _subject("A9", "育児と介護", Department.ACCOUNTING, Term.SPRING, "石坂公俊"),
        _subject("B1", "育児と介護", Department.MANAGEMENT, Term.SPRING, "石坂公俊",
                 is_joint=False),
        _subject("B2", "育児と介護", Department.MANAGEMENT, Term.SPRING, "石坂公俊"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id == subjects[2].joint_id
    assert subjects[1].joint_id is None


def test_non_joint_subjects_are_ignored():
    subjects = [
        _subject("A5", "簿記論", Department.ACCOUNTING, Term.SPRING, "松田流輝", is_joint=False),
        _subject("B5", "簿記論", Department.MANAGEMENT, Term.SPRING, "松田流輝", is_joint=False),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_junior_college_is_outside_the_joint_scope():
    # 合同(経・会) 列は大学シートにしかない。短大は同名・同教員でも対象外
    subjects = [
        _subject("A6", "マーケティングプロジェクト", Department.ACCOUNTING, Term.SPRING, "増渕賢一郎"),
        _subject("J6", "マーケティングプロジェクト", Department.JUNIOR, Term.SPRING, "増渕賢一郎",
                 is_joint=False),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_joint_ids_are_distinct_between_groups():
    subjects = [
        _subject("A7", "科目甲", Department.ACCOUNTING, Term.SPRING, "教員甲"),
        _subject("B7", "科目甲", Department.MANAGEMENT, Term.SPRING, "教員甲"),
        _subject("A8", "科目乙", Department.ACCOUNTING, Term.SPRING, "教員乙"),
        _subject("B8", "科目乙", Department.MANAGEMENT, Term.SPRING, "教員乙"),
    ]
    assign_joint_ids(subjects)
    assert subjects[0].joint_id != subjects[2].joint_id


def test_paired_members_always_span_both_departments():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assign_joint_ids(subjects)

    groups: dict[str, set] = {}
    for subject in subjects:
        if subject.joint_id:
            groups.setdefault(subject.joint_id, set()).add(subject.department)
    assert groups
    assert all(
        departments == {Department.MANAGEMENT, Department.ACCOUNTING}
        for departments in groups.values()
    )


def test_real_workbook_has_no_flag_mismatch():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assert assign_joint_ids(subjects) == []
