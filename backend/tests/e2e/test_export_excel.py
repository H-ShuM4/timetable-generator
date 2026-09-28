"""Excel の書き出しを実ブラウザで確かめる。

**出力は Excel だけ。** 画面を印刷して PDF にする道も持っていたが、
事務局の様式に合わせた xlsx が組めるようになったので畳んだ。

中身の検分は tests/test_excel_writer.py が担う。ここで見るのは、出力の
ボタンから実際にファイルが届くところまで。fetch とダウンロードが絡むので
DOM スタブでは通せない。
"""
import openpyxl
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import generate_in_mock_mode

pytestmark = pytest.mark.e2e


def test_the_button_hands_over_a_workbook(page: Page, live_server, sample_xlsx):
    generate_in_mock_mode(page, live_server, sample_xlsx)

    with page.expect_download() as download:
        page.locator("#export-button").click()
    assert download.value.suggested_filename == "時間割.xlsx"


def test_the_workbook_holds_the_six_sheets_the_office_expects(
    page: Page, live_server, sample_xlsx, tmp_path
):
    """届いたファイルが実際に開けること。

    サーバ側の検分は通っていても、経路の途中（media type、一時ファイルの
    後始末）で壊れると事務局の手元には開けないファイルが残る。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)

    with page.expect_download() as download:
        page.locator("#export-button").click()
    saved = tmp_path / "時間割.xlsx"
    download.value.save_as(saved)

    book = openpyxl.load_workbook(saved)
    assert book.sheetnames == [
        "経営・前期", "経営・後期", "会計・前期", "会計・後期",
        "短大・前期", "短大・後期",
    ]
    assert book["経営・前期"]["A1"].value == "経営学科　前期"


def test_the_toolbar_offers_nothing_to_choose(page: Page, live_server, sample_xlsx):
    """形式のプルダウンは残っていない。押せば Excel が出る、それだけ。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)

    expect(page.locator("#export-button")).to_have_text("Excel で出力")
    assert page.locator("#export-format").count() == 0
    assert page.locator("#print-sheets").count() == 0
