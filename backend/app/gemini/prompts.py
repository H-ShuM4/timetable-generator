"""Gemini へ渡すプロンプトと、応答の解析。

科目ごとに実行可能な候補コマを列挙して渡すことで、AI は候補から
選ぶだけでよくなり、制約違反が大きく減る。占有済みの情報は教員別に
絞って渡し、トークンを節約する。
"""
import json
import re

from app.constraints.context import Context
from app.models.timeslot import DAYS, PERIODS, TimeSlot
from app.models.timetable import Timetable
from app.scheduler.candidates import feasible_slot_sets

MAX_CANDIDATES_SHOWN = 25
"""1 科目あたりプロンプトに載せる候補数の上限。"""

_LABEL_PATTERN = re.compile(r"^([月火水木金])([1-5])$")
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "placements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "slots": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["code", "slots"],
            },
        }
    },
    "required": ["placements"],
}


def slot_label(slot: TimeSlot) -> str:
    return f"{slot.day}{slot.period}"


def parse_slot_label(label: str) -> TimeSlot:
    match = _LABEL_PATTERN.match(str(label).strip())
    if not match:
        raise ValueError(f"コマの表記が不正です: {label!r}")
    day, period = match.group(1), int(match.group(2))
    if day not in DAYS or period not in PERIODS:
        raise ValueError(f"コマの表記が不正です: {label!r}")
    return TimeSlot(day, period)


def _slots_label(slots: tuple[TimeSlot, ...]) -> str:
    return "+".join(slot_label(slot) for slot in slots)


def _teacher_occupancy(context: Context, timetable: Timetable) -> list[str]:
    used: dict[str, list[str]] = {}
    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None or not subject.teacher:
            continue
        used.setdefault(subject.teacher, []).extend(
            slot_label(slot) for slot in assignment.slots
        )
    return [
        f"- {teacher}: {', '.join(sorted(slots))}"
        for teacher, slots in sorted(used.items())
    ]


def build_placement_prompt(
    context: Context,
    timetable: Timetable,
    codes: list[str],
    *,
    feedback: list[str] | None = None,
) -> str:
    lines: list[str] = [
        "あなたは大学の時間割を作成する担当者です。",
        "以下の科目を、指定された候補の中から 1 つ選んで配置してください。",
        "",
        "## 制約",
        "- 候補として挙げたコマ以外は選ばないでください。",
        "- この依頼の中で配置する科目同士も、同じ教員が同じコマに重ならないようにしてください。",
        "- 同じ学科・同じ年次の必修科目同士を同じコマに置かないでください。",
        "- 同じ教員が同じ曜日に 3 コマ以上連続しないようにしてください。",
        "",
        "## 配置対象",
    ]

    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        options = feasible_slot_sets(context, timetable, subject)[:MAX_CANDIDATES_SHOWN]
        candidates = ", ".join(_slots_label(slots) for slots in options) or "なし"
        quarter = f"/{subject.quarter.value}" if subject.quarter else ""
        lines.append(
            f"- {code} | {subject.name} | {subject.department.value}"
            f"{subject.year}年 | {subject.term.value}{quarter} | "
            f"{subject.category.value} | 担当: {subject.teacher} | "
            f"候補: {candidates}"
        )

    occupancy = _teacher_occupancy(context, timetable)
    if occupancy:
        lines += ["", "## 既に埋まっている教員のコマ", *occupancy]

    if feedback:
        lines += [
            "",
            "## 前回の配置には次の違反がありました。これらを避けて配置し直してください。",
            *[f"- {item}" for item in feedback],
        ]

    lines += [
        "",
        "## 出力形式",
        "次の JSON だけを出力してください。説明文は不要です。",
        '{"placements": [{"code": "科目コード", "slots": ["月1"]}]}',
        "2 コマ必要な科目は slots に 2 件入れてください。",
    ]
    return "\n".join(lines)


def parse_placement_response(text: str) -> dict[str, tuple[TimeSlot, ...]]:
    """応答 JSON を科目コード → コマ集合の辞書に変換する。"""
    cleaned = _FENCE_PATTERN.sub("", str(text)).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"応答を JSON として解釈できません: {error}") from error

    # 応答は信用できない入力なので、形が違えば必ず ValueError にする。
    # 黙って読み飛ばすと科目が時間割から消えたことに誰も気付けない。
    if not isinstance(payload, dict):
        raise ValueError(f"応答がオブジェクトではありません: {type(payload).__name__}")

    placements = payload.get("placements")
    if not isinstance(placements, list):
        raise ValueError("応答に placements 配列がありません")

    result: dict[str, tuple[TimeSlot, ...]] = {}
    for item in placements:
        if not isinstance(item, dict):
            raise ValueError(f"placements の要素が不正です: {item!r}")
        code = str(item.get("code", "")).strip()
        slots = item.get("slots")
        if not code or not isinstance(slots, list) or not slots:
            raise ValueError(f"placements の要素が不正です: {item!r}")
        result[code] = tuple(parse_slot_label(label) for label in slots)
    return result
