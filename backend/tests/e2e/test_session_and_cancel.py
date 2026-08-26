"""読み込み済みデータへ戻る道と、生成を止める道を実ブラウザで確かめる。

どちらも fetch の往復と SSE が絡み、DOM スタブでは通せない。
"""
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import ACTIVE, GENERATION_TIMEOUT_MS, generate_in_mock_mode, load_workbooks

pytestmark = pytest.mark.e2e


def test_a_saved_session_survives_a_cleared_local_storage(
    page: Page, live_server, sample_xlsx
):
    """localStorage の 1 件だけが頼りだと、それを消した途端に過去の
    結果へ手が届かなくなる。サーバには最大 20 件残っている。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)
    expect(page.locator("#timetable-grid .card").first).to_be_visible()

    page.evaluate("() => window.localStorage.clear()")
    page.reload()

    # 覚えていないので復元は起きない。生成タブも閉じたまま。
    expect(page.locator('#tabs button[data-view="generate"]')).to_be_disabled()

    # 一覧は畳んである。読込画面の主役はドラッグ&ドロップで、これは脇道。
    page.locator("#saved-sessions > summary").click()
    saved = page.locator("#saved-session-list button")
    expect(saved.first).to_be_visible()
    saved.first.click()

    expect(page.locator('#tabs button[data-view="generate"]')).to_be_enabled()
    expect(page.locator('#tabs button[data-view="result"]')).to_be_enabled()
    page.locator('#tabs button[data-view="result"]').click()
    expect(page.locator("#timetable-grid .card").first).to_be_visible()


def test_a_generation_can_be_stopped(page: Page, live_server, sample_xlsx):
    """AI モードは数十分かかる。止める手立てが無いと、間違えて始めた
    生成が終わるまで事務局は何もできない。"""
    load_workbooks(page, live_server, sample_xlsx)
    page.locator('#tabs button[data-view="generate"]').click()

    expect(page.locator("#cancel-button")).to_be_disabled()
    page.locator("#generate-button").click()
    expect(page.locator("#cancel-button")).to_be_enabled()
    # ログパネルは画面下端に固定で開く。中止ボタンがその下に隠れていては
    # 押せないので、覆われていないことをここで押さえる。
    with page.expect_response(re.compile(r"/api/generate/.+/cancel")) as response:
        page.locator("#cancel-button").click()
    assert response.value.status == 202

    expect(page.locator("#generate-status")).to_contain_text(
        "中止しました", timeout=GENERATION_TIMEOUT_MS
    )
    # 中止は結果を残さない。結果タブは開かないまま、もう一度始められる。
    expect(page.locator("#view-result")).not_to_have_class(ACTIVE)
    expect(page.locator("#generate-button")).to_be_enabled()
    expect(page.locator("#cancel-button")).to_be_disabled()
