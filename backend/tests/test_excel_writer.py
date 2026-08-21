import openpyxl

from app.constraints.context import Context
from app.export.excel_writer import SHEET_PLAN, write_timetable_excel
from app.models.enums import Department, Quarter, Term
from tests.factories import subject as make
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.pipeline import GenerationResult




def build(subjects, placements, intensive_codes=()):
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    for code, slots in placements.items():
        tt.place(code, slots, AssignmentSource.GEMINI)
    return ctx, GenerationResult(timetable=tt, intensive_codes=list(intensive_codes))


def test_creates_all_seven_sheets(tmp_path):
    ctx, result = build([make("A1")], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    workbook = openpyxl.load_workbook(path)
    assert len(SHEET_PLAN) == 6
    assert workbook.sheetnames == [name for name, _, _ in SHEET_PLAN] + ["集中講義"]


def test_grid_has_day_headers_and_period_labels(tmp_path):
    ctx, result = build([make("A1")], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["経営・前期"]
    assert [sheet.cell(row=1, column=c).value for c in range(2, 7)] == list("月火水木金")
    assert [sheet.cell(row=r, column=1).value for r in range(2, 7)] == [
        "1限", "2限", "3限", "4限", "5限"
    ]


def test_subject_appears_in_correct_cell(tmp_path):
    subject = make("A1", name="経営学入門", teacher="築雅之")
    ctx, result = build([subject], {"A1": (TimeSlot("水", 3),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["経営・前期"]
    cell = sheet.cell(row=4, column=4).value  # 3限 × 水曜
    assert "経営学入門" in cell
    assert "築雅之" in cell


def test_multiple_subjects_share_a_cell(tmp_path):
    a = make("A1", name="科目甲", year=1)
    b = make("A2", name="科目乙", year=2)
    ctx, result = build([a, b], {
        "A1": (TimeSlot("月", 1),),
        "A2": (TimeSlot("月", 1),),
    })
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    cell = openpyxl.load_workbook(path)["経営・前期"].cell(row=2, column=2).value
    assert "科目甲" in cell and "科目乙" in cell
    assert "\n" in cell


def test_quarter_is_annotated(tmp_path):
    subject = make(
        "J1", name="デジタルデザイン", department=Department.JUNIOR, quarter=Quarter.Q1
    )
    ctx, result = build([subject], {"J1": (TimeSlot("火", 2),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    cell = openpyxl.load_workbook(path)["短大・前期"].cell(row=3, column=3).value
    assert "[前①]" in cell


def test_double_slot_subject_appears_in_both_cells(tmp_path):
    subject = make("J1", name="動画制作", department=Department.JUNIOR,
                   slots_required=2, requires_consecutive=True)
    ctx, result = build([subject], {"J1": (TimeSlot("水", 2), TimeSlot("水", 3))})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["短大・前期"]
    assert "動画制作" in sheet.cell(row=3, column=4).value
    assert "動画制作" in sheet.cell(row=4, column=4).value


def test_intensive_sheet_lists_intensive_subjects(tmp_path):
    subject = make("A9", name="集中講義甲", is_intensive=True)
    ctx, result = build([subject], {}, intensive_codes=["A9"])
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["集中講義"]
    assert sheet.cell(row=1, column=1).value == "授業コード"
    assert sheet.cell(row=2, column=1).value == "A9"
    assert sheet.cell(row=2, column=2).value == "集中講義甲"


def test_fall_subject_goes_to_fall_sheet(tmp_path):
    subject = make("A1", name="後期科目", term=Term.FALL)
    ctx, result = build([subject], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    workbook = openpyxl.load_workbook(path)
    assert workbook["経営・前期"].cell(row=2, column=2).value in (None, "")
    assert "後期科目" in workbook["経営・後期"].cell(row=2, column=2).value
