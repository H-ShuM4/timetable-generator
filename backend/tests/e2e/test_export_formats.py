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


def choose_format(page: Page, value: str):
    page.locator("#export-format").select_option(value)


def test_the_term_layout_builds_every_sheet_and_prints(page: Page, live_server, sample_xlsx):
    # 実ブラウザの印刷ダイアログは headless では返ってこない。呼ばれたことだけ数える。
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose_format(page, "pdf")
    page.locator("#export-button").click()

    assert page.evaluate("() => window.__printed") == 1
    headings = page.locator("#print-sheets .print-heading").all_text_contents()
    assert [h.strip() for h in headings] == [
        "経営・前期", "経営・後期", "会計・前期", "会計・後期",
        "短期大学部・前期", "短期大学部・後期", "集中講義",
    ]
    assert page.locator("#print-sheets table.timetable").count() == 6
    assert page.locator("#print-sheets .card").count() > 0


def test_the_sheets_are_dropped_after_printing(page: Page, live_server, sample_xlsx):
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose_format(page, "pdf")
    page.locator("#export-button").click()
    assert page.locator("#print-sheets .print-sheet").count() == 7

    # 実際の印刷後に届くイベント。613 件ぶんを抱えたままにしない。
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    assert page.locator("#print-sheets .print-sheet").count() == 0


def test_every_timetable_sheet_fits_one_page(page: Page, live_server, sample_xlsx):
    """A3 横・1 行カードで 1 区分 1 枚。用紙と詰め方を選ばせない前提。

    事務局が Excel を増やしてここが崩れたら、設定を見直す合図になる。
    末尾の集中講義は表ではなく一覧なので、割れても読めるため見ない。
    """
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose_format(page, "pdf")
    page.locator("#export-button").click()

    # A3 横・余白 10mm を 96dpi の CSS px に直した描画領域は 1512 × 1047
    over = page.evaluate("""() => {
      const box = document.getElementById("print-sheets");
      box.style.cssText =
        "display:block;position:absolute;left:-10000px;top:0;width:1512px";
      const rows = [...box.querySelectorAll(".print-sheet")]
        .filter((s) => s.querySelector("table.timetable"))
        .map((s) => [s.querySelector(".print-heading").textContent.trim(),
                     +(s.getBoundingClientRect().height / 1047).toFixed(2)])
        .filter(([, ratio]) => ratio > 1);
      box.style.cssText = "";
      return rows;
    }""")
    assert over == [], f"1 枚に収まらない区分がある: {over}"


def test_the_print_view_keeps_the_colours_that_carry_meaning(
    page: Page, live_server, sample_xlsx
):
    """print-color-adjust が効いていないと Chrome は背景色を落とす。

    レールの色（配置元）も年次チップの濃淡も消え、この機能の意味が無くなる。
    """
    page.add_init_script(RECORD_PRINT)
    generate_in_mock_mode(page, live_server, sample_xlsx)
    choose_format(page, "pdf")
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


def test_excel_still_downloads_when_chosen(page: Page, live_server, sample_xlsx):
    generate_in_mock_mode(page, live_server, sample_xlsx)

    choose_format(page, "xlsx")
    with page.expect_download() as download:
        page.locator("#export-button").click()
    assert download.value.suggested_filename.endswith(".xlsx")


