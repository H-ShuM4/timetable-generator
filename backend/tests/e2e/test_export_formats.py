"""出力形式の選択を実ブラウザで確かめる。

PDF はブラウザの印刷で出す。DOM スタブは「何を組んだか」までしか見ないので、
出力ボタンから window.print() まで実際につながっているか、印刷メディアで
背景色（レールの色・年次の濃淡）が残るかは、ここでしか分からない。
"""
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import generate_in_mock_mode

pytestmark = pytest.mark.e2e

RECORD_PRINT = """
window.__printed = 0;
window.print = () => { window.__printed += 1; };
"""


def choose(page: Page, **values):
    for name, value in values.items():
        page.evaluate(
            """([id, v]) => { const e = document.getElementById(id);
               e.value = v; e.dispatchEvent(new Event("change", { bubbles: true })); }""",
            [f"export-{name}", value])


def test_the_term_layout_builds_every_sheet_and_prints(page: Page, live_server, sample_xlsx):
    # 実ブラウザの印刷ダイアログは headless では返ってこない。呼ばれたことだけ数える。
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="pdf", unit="term", paper="a3", density="compact")
    page.locator("#export-button").click()

    assert page.evaluate("() => window.__printed") == 1
    headings = page.locator("#print-sheets .print-heading").all_text_contents()
    assert [h.strip() for h in headings] == [
        "経営・前期", "経営・後期", "会計・前期", "会計・後期",
        "短期大学部・前期", "短期大学部・後期", "集中講義",
    ]
    assert page.locator("#print-sheets table.timetable").count() == 6
    assert page.locator("#print-sheets .card").count() > 0


def test_the_department_layout_pairs_the_two_terms(page: Page, live_server, sample_xlsx):
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="pdf", unit="department", paper="a3", density="compact")
    page.locator("#export-button").click()

    headings = page.locator("#print-sheets .print-heading").all_text_contents()
    assert [h.strip() for h in headings] == ["経営", "会計", "短期大学部", "集中講義"]
    assert page.locator("#print-sheets .print-pair").count() == 3
    assert page.locator("#print-sheets table.timetable").count() == 6


def test_the_sheets_are_dropped_after_printing(page: Page, live_server, sample_xlsx):
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="pdf", unit="term", paper="a3", density="compact")
    page.locator("#export-button").click()
    assert page.locator("#print-sheets .print-sheet").count() == 7

    # 実際の印刷後に届くイベント。613 件ぶんを抱えたままにしない。
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    assert page.locator("#print-sheets .print-sheet").count() == 0


def test_the_page_count_is_told_before_printing(page: Page, live_server, sample_xlsx):
    """印刷ダイアログを開くまで何ページになるか分からないのでは遅い。"""
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="pdf", unit="term", paper="a3", density="compact")
    expect(page.locator("#export-note")).to_contain_text("1 枚に収まります")

    choose(page, paper="a4", density="full")  # 2 行カードは A4 に入らない
    expect(page.locator("#export-note")).to_contain_text("収まりません")
    expect(page.locator("#export-note")).to_have_class("hint warn")


def test_the_print_view_keeps_the_colours_that_carry_meaning(
    page: Page, live_server, sample_xlsx
):
    """print-color-adjust が効いていないと Chrome は背景色を落とす。

    レールの色（配置元）も年次チップの濃淡も消え、この機能の意味が無くなる。
    """
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)
    choose(page, format="pdf", unit="term", paper="a3", density="compact")
    page.locator("#export-button").click()

    page.emulate_media(media="print")

    expect(page.locator("main")).to_be_hidden()
    expect(page.locator("#log-panel")).to_be_hidden()
    expect(page.locator("#print-sheets")).to_be_visible()

    adjust, rail, chip = page.evaluate("""() => {
      const card = document.querySelector("#print-sheets .card");
      const s = getComputedStyle(card.querySelector(".card-rail"));
      return [s.printColorAdjust || s.webkitPrintColorAdjust,
              s.backgroundColor,
              getComputedStyle(card.querySelector(".card-year")).backgroundColor];
    }""")
    assert adjust == "exact"
    assert rail not in ("rgba(0, 0, 0, 0)", "transparent"), "レールの色が消えている"
    assert chip not in ("rgba(0, 0, 0, 0)", "transparent"), "年次チップの濃淡が消えている"


def test_pdf_is_the_default_because_that_is_what_the_office_distributes(
    page: Page, live_server, sample_xlsx
):
    """事務局は最終的に PDF にして学生へ配布している。既定をそちらに置く。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)

    expect(page.locator("#export-format")).to_have_value("pdf")
    expect(page.locator("#export-options")).to_be_visible()


def test_excel_still_downloads_when_chosen(page: Page, live_server, sample_xlsx):
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="xlsx")
    expect(page.locator("#export-options")).to_be_hidden()
    with page.expect_download() as download:
        page.locator("#export-button").click()
    assert download.value.suggested_filename.endswith(".xlsx")


def test_the_category_fits_the_term_layout_but_not_the_side_by_side_one(
    page: Page, live_server, sample_xlsx
):
    """区分まで入れると横幅を食う。学科ごとは表の幅が半分なので入りきらない。

    短縮（必／選／選必）でも 1.2 ページだったので、落とす選択肢を用意した。
    """
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose(page, format="pdf", paper="a3", unit="term", density="compact")
    expect(page.locator("#export-note")).to_contain_text("1 枚に収まります")

    choose(page, unit="department")
    expect(page.locator("#export-note")).to_contain_text("収まりません")

    choose(page, density="slim")
    expect(page.locator("#export-note")).to_contain_text("1 枚に収まります")
