"""前年度のファイルが無いとき、踏襲モードが押せないことを実ブラウザで確かめる。

踏襲モードそのものの生成は E2E に足さない。前年度の Excel がリポジトリに無く、
検証はすべて実データで行うという方針（設計仕様 §4.5・§13）と両立しないためである。
**押せないことの確認だけは前年度ファイルが無くてもできる**ので、ここで押さえる。
"""
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import load_workbooks

pytestmark = pytest.mark.e2e


def test_inherit_is_blocked_until_the_previous_year_files_arrive(
    page: Page, live_server, sample_xlsx
):
    """選べるのに何も起きないより、選べない理由が見えるほうがよい。

    以前は前年度ファイル無しでも踏襲モードを選べ、613 件すべてが
    「前年度に存在しない新規科目」として並んだうえ、生成しても 1 件も
    踏襲されないまま普通の生成と同じ結果が返っていた。
    """
    load_workbooks(page, live_server, sample_xlsx)

    # ① の読み込み結果でも、どちらが欠けているか分かること
    summary = page.locator("#upload-summary .breakdown").inner_text()
    assert "前年度の時間割" in summary
    assert "前年度の教員一覧" in summary

    page.locator('#tabs button[data-view="generate"]').click()

    expect(page.locator('input[name="mode"][value="inherit"]')).to_be_disabled()
    expect(page.locator('input[name="mode"][value="mock"]')).to_be_enabled()
    expect(page.locator('input[name="mode"][value="optimize"]')).to_be_enabled()

    note = page.locator("#inherit-note")
    expect(note).to_be_visible()
    expect(note).to_contain_text("前年度の時間割")
    expect(note).to_contain_text("前年度の教員一覧")

    # モックは従来どおり選ばれたままで、生成もできる
    expect(page.locator('input[name="mode"][value="mock"]')).to_be_checked()
    expect(page.locator("#generate-button")).to_be_enabled()
