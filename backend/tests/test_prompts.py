import json

import pytest

from app.constraints.context import Context
from app.gemini.prompts import (
    RESPONSE_SCHEMA,
    build_placement_prompt,
    parse_placement_response,
    parse_slot_label,
    slot_label,
)
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_slot_label_roundtrip():
    assert slot_label(TimeSlot("月", 1)) == "月1"
    assert parse_slot_label("金5") == TimeSlot("金", 5)


def test_parse_slot_label_rejects_garbage():
    with pytest.raises(ValueError):
        parse_slot_label("土1")
    with pytest.raises(ValueError):
        parse_slot_label("月9")


def test_prompt_lists_target_subjects():
    subject = make("A1", name="経営学入門")
    ctx = Context.from_lists([subject], [])
    prompt = build_placement_prompt(ctx, Timetable(), ["A1"])
    assert "A1" in prompt
    assert "経営学入門" in prompt


def test_prompt_includes_feasible_candidates():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "月2" in prompt
    # 月1 は A1 と同教員・同学科年次のため候補から外れる
    assert "月1" not in prompt.split("候補", 1)[1].split("\n")[0]


def test_prompt_includes_teacher_occupancy():
    a, b = make("A1"), make("B1", teacher="教員乙")
    ctx = Context.from_lists([a, b], [
        Teacher("教員甲", TeacherKind.FULL_TIME),
        Teacher("教員乙", TeacherKind.FULL_TIME),
    ])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "教員甲" in prompt


def test_prompt_includes_feedback_when_given():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    prompt = build_placement_prompt(
        ctx, Timetable(), ["A1"], feedback=["A1: [H1] 教員甲が月1で重複しています"]
    )
    assert "前回の配置には次の違反がありました" in prompt
    assert "[H1]" in prompt


def test_parse_response_returns_slots_by_code():
    payload = json.dumps({
        "placements": [
            {"code": "A1", "slots": ["月1"]},
            {"code": "J1", "slots": ["水2", "水3"]},
        ]
    })
    parsed = parse_placement_response(payload)
    assert parsed == {
        "A1": (TimeSlot("月", 1),),
        "J1": (TimeSlot("水", 2), TimeSlot("水", 3)),
    }


def test_parse_response_tolerates_markdown_code_fence():
    payload = '```json\n{"placements": [{"code": "A1", "slots": ["火4"]}]}\n```'
    assert parse_placement_response(payload) == {"A1": (TimeSlot("火", 4),)}


def test_parse_response_raises_on_invalid_json():
    with pytest.raises(ValueError, match="JSON"):
        parse_placement_response("これは JSON ではありません")


def test_parse_response_raises_on_invalid_slot_label():
    payload = json.dumps({"placements": [{"code": "A1", "slots": ["土1"]}]})
    with pytest.raises(ValueError):
        parse_placement_response(payload)


def test_response_schema_declares_placements():
    assert RESPONSE_SCHEMA["type"] == "object"
    assert "placements" in RESPONSE_SCHEMA["properties"]
