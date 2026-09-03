"""生成画面の操作を実ブラウザで確かめる。

重み付けは localStorage、AI の可否はサーバの設定、折り畳みは選んだ
モードと、判断のもとが三方に散っている。どれも画面を開き直した
ときに正しく組み上がるかが要点で、そこは実ブラウザでしか見られない。
"""
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import load_workbooks

pytestmark = pytest.mark.e2e


def open_generate_view(page: Page, live_server, sample_xlsx) -> None:
    load_workbooks(page, live_server, sample_xlsx)
    page.locator('#tabs button[data-view="generate"]').click()


def test_moving_a_weight_updates_its_label_and_survives_a_reload(
    page: Page, live_server, sample_xlsx
):
    """重み付けは数字ではなく言葉で示し、選んだ値は次回まで残す。

    毎年おなじ重み付けで組む事務局が、開くたびに 6 本を引き直さずに
    済むようにするための保存である。
    """
    open_generate_view(page, live_server, sample_xlsx)
    slider = page.locator("#param-list input[type=range]").first
    key = slider.get_attribute("data-key")
    label = page.locator(f'.param-value[data-for="{key}"]')

    before = label.inner_text()
    slider.fill("2")
    slider.dispatch_event("input")
    after = label.inner_text()
    assert after != before, "つまみを動かしても言葉が変わらない"

    page.reload()
    page.locator('#tabs button[data-view="generate"]').click()
    expect(page.locator(f'#param-list input[data-key="{key}"]')).to_have_value("2")
    expect(page.locator(f'.param-value[data-for="{key}"]')).to_have_text(after)


def test_an_unavailable_mode_does_not_stay_selected(
    page: Page, live_server, sample_xlsx
):
    """押せないモードが選ばれたままにならない。

    ここを外すと、選べないはずの踏襲を抱えたまま「生成を開始」が押せて
    しまう。サーバは前年度データが無ければ黙ってモックへ落とすので、
    事務局は前年度を引き継いだつもりの時間割を受け取ることになる。

    重み付けの折り畳みそのものは DOM スタブが見ている（前年度の Excel
    はリポジトリに置けないため、ここでは踏襲を選び切れない）。
    """
    open_generate_view(page, live_server, sample_xlsx)

    page.evaluate("""() => {
      const radio = document.querySelector('input[name="mode"][value="inherit"]');
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }""")

    expect(page.locator('input[name="mode"][value="mock"]')).to_be_checked()
    expect(page.locator('input[name="mode"][value="inherit"]')).not_to_be_checked()


def test_the_ai_mode_cannot_be_chosen_without_a_key(
    page: Page, live_server, sample_xlsx
):
    """キーが無いまま選べると、サーバは黙ってモックへ落とす。

    走り終わってから「AI で作ったつもりだった」と気づくのは遅すぎる。
    選べない理由を画面に出す。
    """
    open_generate_view(page, live_server, sample_xlsx)

    expect(page.locator('input[name="mode"][value="optimize"]')).to_be_disabled()
    note = page.locator("#ai-note")
    expect(note).to_be_visible()
    assert "API キー" in note.inner_text()
    assert "設定" in note.inner_text(), "どこで登録するかが書かれていない"

    # モックと踏襲は塞がない
    expect(page.locator('input[name="mode"][value="mock"]')).to_be_enabled()


def test_the_inherit_mode_says_what_is_missing(page: Page, live_server, sample_xlsx):
    """前年度の 2 本がそろわないと踏襲は 1 件も働かない。

    選べるのに何も起きないより、選べない理由が見えるほうがよい。
    """
    open_generate_view(page, live_server, sample_xlsx)

    expect(page.locator('input[name="mode"][value="inherit"]')).to_be_disabled()
    note = page.locator("#inherit-note")
    expect(note).to_be_visible()
    assert "前年度" in note.inner_text()
    assert "ファイル読込" in note.inner_text(), "どこから読ませるかが書かれていない"


def test_the_retarget_panel_is_hidden_outside_the_inherit_mode(
    page: Page, live_server, sample_xlsx
):
    """組み替え対象は踏襲モードのときだけ意味を持つ。"""
    open_generate_view(page, live_server, sample_xlsx)
    expect(page.locator("#retarget-panel")).to_be_hidden()


def test_the_cancel_button_is_dead_until_a_generation_starts(
    page: Page, live_server, sample_xlsx
):
    """止めるものが無いのに押せると、押した人は何が起きたか分からない。"""
    open_generate_view(page, live_server, sample_xlsx)
    expect(page.locator("#cancel-button")).to_be_disabled()
    expect(page.locator("#generate-button")).to_be_enabled()
