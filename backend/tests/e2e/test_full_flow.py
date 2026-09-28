"""読込から Excel 出力まで、事務局がたどる道を実ブラウザで 1 本通す。

`tests/js` の DOM スタブは「何を書き出したか」までしか見ない。fetch の
往復・SSE・HTML5 ドラッグ&ドロップ・ダウンロードは実機でしか壊れ方が
分からず、実際そこで不具合が続いた。モックモードなら Gemini の無料枠を
使わず決定的に走るので、その道だけは自動で踏み直せる。
"""
import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ACTIVE = re.compile(r"\bactive\b")

GENERATION_TIMEOUT_MS = 180_000
"""モック生成の待ち。ソルバの見直し時間を含めても十分な上限。"""


def test_excel_goes_in_a_timetable_comes_out(page: Page, live_server, sample_xlsx):
    page.goto(live_server)

    # ---- ① 読込 ----------------------------------------------------------
    page.locator("#file-input").set_input_files(sample_xlsx)
    # 役割はファイル名から推測される。カリキュラムと教員が揃って初めて押せる。
    expect(page.locator("#upload-button")).to_be_enabled()
    page.locator("#upload-button").click()

    expect(page.locator("#upload-summary .stat-value").first).to_be_visible()
    subject_count = page.locator("#upload-summary .stat-value").first.inner_text()
    assert int(subject_count) > 0, "科目が 1 件も読めていない"

    generate_tab = page.locator('#tabs button[data-view="generate"]')
    expect(generate_tab).to_be_enabled()

    # ---- ② 生成 ----------------------------------------------------------
    generate_tab.click()
    expect(page.locator('input[name="mode"][value="mock"]')).to_be_checked()
    page.locator("#generate-button").click()

    # ログが SSE で流れてくること。ここが死ぬと利用者は無言の画面を見続ける。
    expect(page.locator("#log-body")).not_to_be_empty(timeout=GENERATION_TIMEOUT_MS)

    # 完了すると結果タブへ自動で切り替わる。
    expect(page.locator("#view-result")).to_have_class(
        ACTIVE, timeout=GENERATION_TIMEOUT_MS
    )
    expect(page.locator("#generate-status")).to_contain_text("完了")

    # ---- ③ 結果 ----------------------------------------------------------
    cards = page.locator("#timetable-grid .card")
    expect(cards.first).to_be_visible()
    assert cards.count() > 0
    expect(page.locator("#count-violations")).to_be_visible()

    # ---- ④ コマの移動 ----------------------------------------------------
    # 落とした先が制約に触れれば alert で拒否される。どちらに転んでも正しい
    # 振る舞いなので、ここで確かめるのは「ドラッグがサーバまで届くこと」。
    # 空のセルが偶然妥当かどうかに結果を委ねると、テストが日替わりになる。
    page.on("dialog", lambda dialog: dialog.accept())
    empty_cell = page.locator("#timetable-grid td:not(:has(.card))").first
    expect(empty_cell).to_be_visible()

    with page.expect_request(re.compile(r"/api/result/.+/move")) as request:
        cards.first.drag_to(empty_cell)
    assert request.value.method == "POST"

    # ---- ⑤ Excel 出力 ----------------------------------------------------
    with page.expect_download() as download:
        page.locator("#export-button").click()
    assert download.value.suggested_filename.endswith(".xlsx")
