"""生成結果を時間割表マトリクスの Excel として書き出す。

学科 × 学期で 6 シート。集中講義は別シートに一覧で出す。
"""
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from app.constraints.context import Context
from app.models.enums import Department, Term
from app.models.timeslot import DAYS, PERIODS, TimeSlot

SHEET_PLAN: tuple[tuple[str, Department, Term], ...] = (
    ("経営・前期", Department.MANAGEMENT, Term.SPRING),
    ("経営・後期", Department.MANAGEMENT, Term.FALL),
    ("会計・前期", Department.ACCOUNTING, Term.SPRING),
    ("会計・後期", Department.ACCOUNTING, Term.FALL),
    ("短大・前期", Department.JUNIOR, Term.SPRING),
    ("短大・後期", Department.JUNIOR, Term.FALL),
)

INTENSIVE_SHEET = "集中講義"
_HEADER_FONT = Font(bold=True)
_CELL_ALIGNMENT = Alignment(wrap_text=True, vertical="top")


def _describe(subject) -> str:
    quarter = f"[{subject.quarter.value}]" if subject.quarter else ""
    return (
        f"{subject.name}{quarter}\n"
        f"{subject.teacher}\n"
        f"{subject.year}年・{subject.category.value}"
    )


def _write_grid(sheet, context: Context, timetable, department: Department, term: Term) -> None:
    sheet.cell(row=1, column=1, value="").font = _HEADER_FONT
    for column, day in enumerate(DAYS, start=2):
        cell = sheet.cell(row=1, column=column, value=day)
        cell.font = _HEADER_FONT
        sheet.column_dimensions[cell.column_letter].width = 28

    for row, period in enumerate(PERIODS, start=2):
        sheet.cell(row=row, column=1, value=f"{period}限").font = _HEADER_FONT
        sheet.row_dimensions[row].height = 72
        for column, day in enumerate(DAYS, start=2):
            entries = []
            for code in timetable.occupied_by(TimeSlot(day, period)):
                subject = context.subjects.get(code)
                if subject is None:
                    continue
                if subject.department is department and subject.term is term:
                    entries.append(_describe(subject))
            cell = sheet.cell(row=row, column=column, value="\n\n".join(entries))
            cell.alignment = _CELL_ALIGNMENT


def _write_intensive(sheet, context: Context, codes: list[str]) -> None:
    headers = ("授業コード", "科目名", "学科", "年次", "開講期", "科目区分", "教員")
    for column, title in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=title)
        cell.font = _HEADER_FONT
        sheet.column_dimensions[cell.column_letter].width = 20

    for row, code in enumerate(codes, start=2):
        subject = context.subjects.get(code)
        if subject is None:
            continue
        values = (
            subject.code, subject.name, subject.department.value, subject.year,
            subject.term.value, subject.category.value, subject.teacher,
        )
        for column, value in enumerate(values, start=1):
            sheet.cell(row=row, column=column, value=value)


def write_timetable_excel(context: Context, result, path: str | Path) -> Path:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    for name, department, term in SHEET_PLAN:
        sheet = workbook.create_sheet(name)
        _write_grid(sheet, context, result.timetable, department, term)

    _write_intensive(
        workbook.create_sheet(INTENSIVE_SHEET), context, list(result.intensive_codes)
    )

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target
