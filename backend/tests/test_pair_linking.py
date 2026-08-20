"""前期・後期をまたぐ対応付けと H12。"""
import json

import pytest

from app.constraints.context import Context
from app.constraints.subject_rules import check_h12
from app.ingest.pair_linking import assign_pair_ids, load_pair_config
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable

CONFIG = {
    "same_slot_across_terms": [["科目Ⅰ", "科目Ⅱ"]],
    "adjacent_periods": [["課題研究Ⅰ", "卒業研究Ⅰ"]],
}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "paired_subjects.json"
    path.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    return path


def make(code, base_name, teacher, term, year=1, department=Department.MANAGEMENT):
    return Subject(
        code=code, name=code, base_name=base_name, department=department, year=year,
        term=term, quarter=None, category=Category.REQUIRED, teacher=teacher,
    )


def test_pairs_the_same_teacher_across_terms(config_path):
    spring = make("S1", "科目Ⅰ", "教員甲", Term.SPRING)
    fall = make("F1", "科目Ⅱ", "教員甲", Term.FALL)
    assign_pair_ids([spring, fall], config_path)
    assert spring.pair_id and spring.pair_id == fall.pair_id


def test_does_not_pair_different_teachers(config_path):
    spring = make("S1", "科目Ⅰ", "教員甲", Term.SPRING)
    fall = make("F1", "科目Ⅱ", "教員乙", Term.FALL)
    assign_pair_ids([spring, fall], config_path)
    assert spring.pair_id is None and fall.pair_id is None


def test_does_not_pair_across_departments(config_path):
    spring = make("S1", "科目Ⅰ", "教員甲", Term.SPRING)
    fall = make("F1", "科目Ⅱ", "教員甲", Term.FALL, department=Department.ACCOUNTING)
    assign_pair_ids([spring, fall], config_path)
    assert spring.pair_id is None and fall.pair_id is None


def test_a_teacher_with_two_sections_pairs_them_in_code_order(config_path):
    subjects = [
        make("S2", "科目Ⅰ", "教員甲", Term.SPRING),
        make("S1", "科目Ⅰ", "教員甲", Term.SPRING),
        make("F2", "科目Ⅱ", "教員甲", Term.FALL),
        make("F1", "科目Ⅱ", "教員甲", Term.FALL),
    ]
    assign_pair_ids(subjects, config_path)
    by = {s.code: s for s in subjects}
    assert by["S1"].pair_id == by["F1"].pair_id
    assert by["S2"].pair_id == by["F2"].pair_id
    assert by["S1"].pair_id != by["S2"].pair_id


def test_a_term_without_a_partner_is_left_alone(config_path):
    spring = make("S1", "科目Ⅰ", "教員甲", Term.SPRING)
    assign_pair_ids([spring], config_path)
    assert spring.pair_id is None


def test_adjacent_ids_link_the_two_seminar_years(config_path):
    third = make("T1", "課題研究Ⅰ", "教員甲", Term.SPRING, year=3)
    fourth = make("F1", "卒業研究Ⅰ", "教員甲", Term.SPRING, year=4)
    assign_pair_ids([third, fourth], config_path)
    assert third.adjacent_id and third.adjacent_id == fourth.adjacent_id
    # 隣接は好みなので pair_id は付かない
    assert third.pair_id is None


def test_a_missing_config_disables_the_feature(tmp_path):
    assert load_pair_config(tmp_path / "absent.json") == {
        "same_slot_across_terms": [], "adjacent_periods": []
    }


def test_a_broken_config_disables_the_feature(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    assert load_pair_config(path)["same_slot_across_terms"] == []


def _paired_context(config_path):
    spring = make("S1", "科目Ⅰ", "教員甲", Term.SPRING)
    fall = make("F1", "科目Ⅱ", "教員甲", Term.FALL)
    assign_pair_ids([spring, fall], config_path)
    return Context.from_lists([spring, fall], []), spring, fall


def test_h12_requires_the_same_slot(config_path):
    ctx, spring, fall = _paired_context(config_path)
    tt = Timetable()
    tt.place("S1", (TimeSlot("月", 2),), AssignmentSource.SOLVER)
    assert check_h12(ctx, tt, fall, (TimeSlot("月", 2),)) == []
    violations = check_h12(ctx, tt, fall, (TimeSlot("火", 2),))
    assert [v.rule_id for v in violations] == ["H12"]
    assert violations[0].related_code == "S1"


def test_h12_ignores_a_partner_that_is_not_placed_yet(config_path):
    ctx, _, fall = _paired_context(config_path)
    assert check_h12(ctx, Timetable(), fall, (TimeSlot("火", 2),)) == []


def test_h12_ignores_subjects_without_a_pair(config_path):
    subject = make("X1", "その他", "教員甲", Term.SPRING)
    ctx = Context.from_lists([subject], [])
    assert check_h12(ctx, Timetable(), subject, (TimeSlot("月", 1),)) == []
