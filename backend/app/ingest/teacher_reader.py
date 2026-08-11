"""教員一覧 Excel を Teacher の辞書に変換する。"""
import re
from pathlib import Path

import openpyxl

from app.ingest.name_normalizer import normalize_name
from app.models.enums import TeacherKind
from app.models.teacher import Teacher
from app.models.timeslot import DAYS, TimeSlot

FULL_TIME_SHEETS = ("大学専任", "短大専任")
"""専任シートの名前。末尾に空白が付いている場合があるため前方一致で探す。"""

PART_TIME_SHEET = "非常勤"

_SEPARATORS = re.compile(r"[,、\s]+")
_SLOT_PATTERN = re.compile(r"^([月火水木金])([1-5])$")


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [token for token in _SEPARATORS.split(str(raw).strip()) if token]


def parse_available_slots(raw: str | None) -> set[TimeSlot]:
    """`月2,月3,月4` 形式を TimeSlot の集合に変換する。

    解釈できないトークンは黙って無視せず、呼び出し側が気付けるよう
    ValueError を投げる。
    """
    slots: set[TimeSlot] = set()
    for token in _split(raw):
        match = _SLOT_PATTERN.match(token)
        if not match:
            raise ValueError(f"出勤可能日の書式が不正です: {token!r}")
        slots.add(TimeSlot(match.group(1), int(match.group(2))))
    return slots


def parse_days(raw: str | None) -> set[str]:
    """`水,木` 形式を曜日の集合に変換する。"""
    days: set[str] = set()
    for token in _split(raw):
        if token not in DAYS:
            raise ValueError(f"曜日の書式が不正です: {token!r}")
        days.add(token)
    return days


def _find_sheet(workbook, prefix: str):
    for name in workbook.sheetnames:
        if name.strip() == prefix:
            return workbook[name]
    return None


def read_teachers(path: str | Path) -> dict[str, Teacher]:
    """教員一覧を読み、正規化済み氏名をキーにした辞書を返す。"""
    workbook = openpyxl.load_workbook(path, data_only=True)
    teachers: dict[str, Teacher] = {}

    for sheet_name in FULL_TIME_SHEETS:
        sheet = _find_sheet(workbook, sheet_name)
        if sheet is None:
            continue
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_name = row[0] if row else None
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            research_day = str(row[1]).strip() if len(row) > 1 and row[1] else None
            special_days = parse_days(row[2] if len(row) > 2 else None)
            kind = TeacherKind.SPECIAL if special_days else TeacherKind.FULL_TIME
            teachers[name] = Teacher(
                name=name,
                kind=kind,
                research_day=research_day,
                available_days=special_days,
            )

    sheet = _find_sheet(workbook, PART_TIME_SHEET)
    if sheet is not None:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_name = row[0] if row else None
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            teachers[name] = Teacher(
                name=name,
                kind=TeacherKind.PART_TIME,
                available_slots=parse_available_slots(row[1] if len(row) > 1 else None),
            )

    return teachers
