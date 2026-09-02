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


def test_most_pairs_span_both_departments_and_the_rest_share_a_subject():
    """合同のほとんどは経営×会計だが、同一学科内のものもある。

    経営情報活用（A）と【再】は経営 2 年前期・築雅之で一緒に開く。
    学科をまたぐことは条件ではないので、どちらの形も許す。ただし
    **同一学科の組は同じ科目・同じ教員・同じ開講期でなければならない。**
    """
    subjects = read_curriculum(CURRICULUM_XLSX)
    assign_joint_ids(subjects)

    groups: dict[str, list] = {}
    for subject in subjects:
        if subject.joint_id:
            groups.setdefault(subject.joint_id, []).append(subject)
    assert groups

    both = {Department.MANAGEMENT, Department.ACCOUNTING}
    for members in groups.values():
        departments = {m.department for m in members}
        if departments == both:
            continue
        assert len(departments) == 1, "経営・会計以外の学科が合同に混ざっている"
        assert len({m.class_group for m in members}) == 1
        assert len({m.teacher for m in members}) == 1


def test_real_workbook_has_no_flag_mismatch():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assert assign_joint_ids(subjects) == []


def test_a_retake_class_joins_the_regular_class_it_is_held_with():
    """経営情報活用（A）と経営情報活用【再】は同一科目で合同開講。

    事務局はどちらにも合同フラグを立てている。同じ教員が同じ開講期に
    同じ科目として一緒に開くので、同じコマに置かなければならない。

    以前は 2 つの理由で組めなかった。（A）が base_name に残ってクラス記号
    違いになること、そして合同グループが経営×会計にまたがることを
    求めていたこと。どちらも同一学科内の合同を想定していなかった。
    """
    subjects = [
        _subject("B57301", "経営情報活用（A）", Department.MANAGEMENT, Term.SPRING, "築雅之"),
        _subject("B57303", "経営情報活用", Department.MANAGEMENT, Term.SPRING, "築雅之"),
    ]
    assign_joint_ids(subjects)

    assert subjects[0].joint_id is not None
    assert subjects[0].joint_id == subjects[1].joint_id


def test_the_full_width_parenthesis_is_a_class_marker_too():
    subjects = read_curriculum(CURRICULUM_XLSX)
    activation = {s.name: s for s in subjects if "経営情報活用" in s.name}
    assert set(activation) == {"経営情報活用（A）", "経営情報活用（B）", "経営情報活用【再】"}
    assert activation["経営情報活用（A）"].class_group == "経営情報活用"
    assert activation["経営情報活用【再】"].class_group == "経営情報活用"


def test_a_multi_character_parenthesis_stays_part_of_the_name():
    """（日本国憲法を含む）や（Photoshop）は科目名の一部でクラス記号ではない。"""
    subjects = read_curriculum(CURRICULUM_XLSX)
    for subject in subjects:
        if "（日本国憲法を含む）" in subject.name or "（Photoshop）" in subject.name:
            assert "（" in subject.class_group, subject.name


def test_the_office_data_still_pairs_every_joint_group_two_at_a_time():
    """合同は必ず 2 件 1 組。3 件以上に膨らんだら鍵の取り方が緩すぎる。

    件数そのものは事務局が Excel を更新するたびに動くので固定しない。
    """
    subjects = read_curriculum(CURRICULUM_XLSX)
    assign_joint_ids(subjects)
    groups = {}
    for subject in subjects:
        if subject.joint_id:
            groups.setdefault(subject.joint_id, []).append(subject)

    assert groups, "合同グループが 1 つも作れていない"
    assert {len(g) for g in groups.values()} == {2}
    for members in groups.values():
        assert len({m.class_group for m in members}) == 1
        assert len({m.teacher for m in members}) == 1
        assert len({m.term for m in members}) == 1
