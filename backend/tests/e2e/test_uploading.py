"""読込画面を実ブラウザで確かめる。

他の E2E は input[type=file] へ直接流し込んでいる。事務局が実際に使う
のはドラッグ&ドロップのほうで、そちらは別の配線を通る。役割の割り当ても
画面でしか組み立たない。
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

DROP_FILES = """(names) => {
  const transfer = new DataTransfer();
  for (const name of names) {
    transfer.items.add(new File(["dummy"], name,
      { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
  }
  document.getElementById("dropzone")
    .dispatchEvent(new DragEvent("drop", { dataTransfer: transfer, bubbles: true }));
}"""


def test_files_dropped_on_the_zone_are_taken_up(page: Page, live_server):
    """点線の枠へ落とすと、ファイル選択と同じところへ入る。

    中身は見ない。落としたものが拾われ、役割の欄が組み上がるかだけを見る
    （読み込みそのものは他のテストが実データで通している）。
    """
    page.goto(live_server)
    page.evaluate(DROP_FILES, ["カリキュラム一覧.xlsx", "教員一覧.xlsx"])

    expect(page.locator("#file-assign select")).to_have_count(2)
    expect(page.locator("#file-assign")).to_contain_text("カリキュラム一覧.xlsx")
    expect(page.locator("#file-assign")).to_contain_text("教員一覧.xlsx")


def test_the_role_is_guessed_from_the_file_name(page: Page, live_server):
    """ファイル名に「前年度」が入っていれば自動で割り当たる。

    事務局は 4 本まとめて投げ込む。毎回 4 つの欄を選び直すのでは、
    自動判定が無いのと変わらない。

    **前年度の 2 本だけを落とす。** 4 本まとめて落とすと、今年度の 2 本が
    先に埋まった残りとして前年度が当たるため、名前を見ていなくても
    答えが合ってしまう（実際、判定を潰しても通った）。
    """
    page.goto(live_server)
    page.evaluate(DROP_FILES, ["前年度_時間割.xlsx", "前年度_教員一覧.xlsx"])

    chosen = page.locator("#file-assign select").evaluate_all(
        "(nodes) => nodes.map((n) => n.value)"
    )
    assert chosen == ["previous_curriculum", "previous_teachers"], \
        f"名前からの割り当てが合っていない: {chosen}"
    # 今年度が無いので、そろうまで読み込めない
    expect(page.locator("#upload-button")).to_be_disabled()


def test_the_teacher_list_is_told_apart_from_the_curriculum(page: Page, live_server):
    """「教員」を含む名前は教員一覧に当てる。順番ではなく名前で決める。"""
    page.goto(live_server)
    page.evaluate(DROP_FILES, ["教員一覧.xlsx", "カリキュラム一覧.xlsx"])

    chosen = page.locator("#file-assign select").evaluate_all(
        "(nodes) => nodes.map((n) => n.value)"
    )
    assert chosen == ["teachers", "curriculum"], \
        f"落とした順に当てはめている: {chosen}"


def test_the_role_can_be_corrected_by_hand(page: Page, live_server):
    """名前に手掛かりが無いときは、欄で選び直せる。"""
    page.goto(live_server)
    page.evaluate(DROP_FILES, ["book1.xlsx", "book2.xlsx"])

    first = page.locator("#file-assign select").first
    first.select_option("previous_curriculum")
    expect(first).to_have_value("previous_curriculum")


def test_the_button_waits_until_both_of_this_year_are_present(page: Page, live_server):
    """カリキュラム一覧と教員一覧がそろうまで読み込めない。

    片方だけで押せると、足りないまま進んで生成の途中で気づくことになる。
    """
    page.goto(live_server)
    expect(page.locator("#upload-button")).to_be_disabled()

    page.evaluate(DROP_FILES, ["カリキュラム一覧.xlsx"])
    expect(page.locator("#upload-button")).to_be_disabled()
    expect(page.locator("#upload-hint")).to_be_visible()

    page.evaluate(DROP_FILES, ["教員一覧.xlsx"])
    expect(page.locator("#upload-button")).to_be_enabled()


def test_the_later_steps_are_locked_until_something_is_loaded(page: Page, live_server):
    """読込が済むまで「生成」「結果」は押せない。左から順に進ませる。"""
    page.goto(live_server)
    expect(page.locator('#tabs button[data-view="generate"]')).to_be_disabled()
    expect(page.locator('#tabs button[data-view="result"]')).to_be_disabled()
    # 設定はその流れの外にあるので、いつでも開ける
    expect(page.locator('#tabs button[data-view="settings"]')).to_be_enabled()
