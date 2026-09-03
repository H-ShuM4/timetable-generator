"""設定画面を実ブラウザで確かめる。

API キーは全文を返さない。保存できたことも、いま入っていることも、
マスクされた文字列だけで伝える。その往復は fetch を挟むので、
DOM スタブでは通せない。

**このファイルはキーを残さない。** サーバは E2E 全体で 1 つを使い回して
おり、キーを置いたままにすると AI モードのゲートを見るテストが、
実行順によって落ちたり通ったりする。最後に必ず消し、消えたことまで
見届ける。
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

FAKE_KEY = "AIzaSyTESTKEY0123456789"


def open_settings(page: Page, live_server: str) -> None:
    page.goto(live_server)
    page.locator('#tabs button[data-view="settings"]').click()


def test_a_saved_key_is_shown_masked_and_can_be_deleted(page: Page, live_server):
    """全文は返さない。先頭だけを見せ、末尾は必ず隠す。"""
    open_settings(page, live_server)
    expect(page.locator("#api-key-status")).to_have_text("未設定")

    page.locator("#api-key").fill(FAKE_KEY)
    page.locator("#save-key").click()

    expect(page.locator("#settings-status")).to_have_text("API キーを保存しました")
    status = page.locator("#api-key-status")
    expect(status).to_contain_text("保存済み")
    shown = status.inner_text()
    assert FAKE_KEY not in shown, f"キーの全文が画面に出ている: {shown}"
    assert FAKE_KEY[-4:] not in shown, "末尾が隠れていない"
    # 入力欄も空に戻す。肩越しに覗かれる余地を残さない。
    expect(page.locator("#api-key")).to_have_value("")

    # 開き直しても保存されている
    open_settings(page, live_server)
    expect(page.locator("#api-key-status")).to_contain_text("保存済み")

    page.locator("#delete-key").click()
    expect(page.locator("#settings-status")).to_have_text("API キーを削除しました")
    expect(page.locator("#api-key-status")).to_have_text("未設定")

    # 後片付けができたことまで見届ける（このファイルの前提）
    open_settings(page, live_server)
    expect(page.locator("#api-key-status")).to_have_text("未設定")


def test_saving_an_empty_key_says_so_instead_of_clearing_it(page: Page, live_server):
    """空のまま押しても、黙って何も起きないことにはしない。"""
    open_settings(page, live_server)
    page.locator("#api-key").fill("   ")
    page.locator("#save-key").click()

    status = page.locator("#settings-status")
    expect(status).to_have_text("API キーを入力してください")
    expect(status).to_have_class("log-ERROR")
    expect(page.locator("#api-key-status")).to_have_text("未設定")


def test_the_model_and_retry_count_survive_a_reload(page: Page, live_server):
    """モデルと再試行回数はサーバに残る。ブラウザを変えても同じ。"""
    open_settings(page, live_server)
    page.locator("#model").fill("gemini-2.5-pro")
    page.locator("#max-retries").fill("5")
    page.locator("#save-settings").click()
    expect(page.locator("#settings-status")).to_have_text("設定を保存しました")

    open_settings(page, live_server)
    expect(page.locator("#model")).to_have_value("gemini-2.5-pro")
    expect(page.locator("#max-retries")).to_have_value("5")

    # 既定へ戻す。あとのテストが引きずらないように。
    page.locator("#model").fill("gemini-2.5-flash")
    page.locator("#max-retries").fill("3")
    page.locator("#save-settings").click()
    expect(page.locator("#settings-status")).to_have_text("設定を保存しました")


def test_the_developer_section_stays_folded(page: Page, live_server):
    """予備モデルは開発用。実務では開かないので、畳んだまま置く。"""
    open_settings(page, live_server)
    assert page.locator("#dev-settings").get_attribute("open") is None
    expect(page.locator("#dev-settings")).to_contain_text("実務では何も選ばないでください")
