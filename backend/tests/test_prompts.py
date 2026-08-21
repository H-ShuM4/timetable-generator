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
from app.models.enums import TeacherKind
from app.models.teacher import Teacher
from tests.factories import subject as make
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable




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


def test_prompt_shows_where_this_chunk_s_teachers_already_are():
    """配置する科目の担当教員が、既にどのコマを持っているかを伝える。"""
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "教員甲: 月1" in prompt


def test_prompt_leaves_out_teachers_this_chunk_never_touches():
    """時間割が埋まると全教員の占有がプロンプトの 76% を占めていた。
    このリクエストに関係しない教員は載せない。"""
    a, b = make("A1", teacher="無関係先生"), make("B1", teacher="担当先生")
    ctx = Context.from_lists([a, b], [
        Teacher("無関係先生", TeacherKind.FULL_TIME),
        Teacher("担当先生", TeacherKind.FULL_TIME),
    ])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "無関係先生" not in prompt


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


@pytest.mark.parametrize("payload", [
    "[]",                                              # 最上位が配列
    '"placements"',                                    # 最上位が文字列
    "{}",                                              # placements が無い
    '{"placements": null}',                            # placements が配列でない
    '{"placements": ["A1"]}',                          # 要素がオブジェクトでない
    '{"placements": [{"code": "A1"}]}',                # slots キーが無い
    '{"placements": [{"code": "A1", "slots": []}]}',   # slots が空
    '{"placements": [{"code": "A1", "slots": "月1"}]}',  # slots が配列でない
    '{"placements": [{"code": "", "slots": ["月1"]}]}',  # code が空
])
def test_parse_response_rejects_malformed_payloads(payload):
    # 黙って読み飛ばすと科目が時間割から消える。必ず ValueError にする
    with pytest.raises(ValueError):
        parse_placement_response(payload)


def test_response_schema_declares_placements():
    assert RESPONSE_SCHEMA["type"] == "object"
    assert "placements" in RESPONSE_SCHEMA["properties"]


def _prompt_for(subject, subjects=None, timetable=None):
    ctx = Context.from_lists(subjects or [subject], [])
    return build_placement_prompt(ctx, timetable or Timetable(), [subject.code])


def test_prompt_asks_for_periods_one_to_four():
    """ソルバーだけでなく AI にも 1〜4 限への集約を伝える。"""
    text = _prompt_for(make("A1"))
    assert "できるだけ 1〜4 限に置いてください" in text


def test_prompt_states_the_consecutive_limit():
    assert "4 コマ以上連続しないように" in _prompt_for(make("A1"))


def test_candidates_are_listed_in_preference_order():
    """5 限より前の時限が先に並ぶ。上限で切られても望ましい候補が残る。"""
    subject = make("A1")
    line = next(
        line for line in _prompt_for(subject).splitlines() if line.startswith("- A1 |")
    )
    candidates = line.split("候補: ", 1)[1].split(", ")
    assert candidates[0].endswith(("1", "2", "3", "4"))
    fifth = [i for i, c in enumerate(candidates) if c.endswith("5")]
    earlier = [i for i, c in enumerate(candidates) if not c.endswith("5")]
    assert not fifth or not earlier or min(fifth) > max(earlier)
