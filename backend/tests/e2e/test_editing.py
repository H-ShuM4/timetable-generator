"""結果画面の編集操作を実ブラウザで確かめる。

DOM スタブは「何を書き出したか」までしか見ない。Undo は move の応答に
乗ってきた「触れた科目と移動前のコマ」を画面が積み直す仕組みで、
fetch の往復が絡むためスタブでは通せない。

**踏襲モードはここに足さない。** 前年度の Excel がリポジトリに無く、
検証はすべて実データで行うという方針（設計仕様 §4.5）と両立しない。
"""
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import generate_in_mock_mode

pytestmark = pytest.mark.e2e


def test_undo_puts_the_card_back_where_it_came_from(page: Page, live_server, sample_xlsx):
    """まとまりは最大 4 科目が同時に動く。落とす場所を間違えたときの
    手戻りが大きいので、1 手で戻せること自体を守る。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)
    page.on("dialog", lambda dialog: dialog.accept())

    # 実データの時間割はほぼ埋まっている（経営・前期は 25 コマ中 3 つしか
    # 空いていない）。どのカードがどこへ動かせるかはデータ次第なので、
    # 動かせる組み合わせを先に 1 つ見つけてから、その 1 手をドラッグで行う。
    # 確かめたいのは制約の判定ではなく、掴んで落として取り消せることである。
    #
    # **1 コマに 1 枚しか無いカードを選ぶ。** 9 枚が重なるコマもあり、
    # ドラッグの当たり判定は目当てのカードではなく手前の 1 枚を掴む。
    # 実際それで別の科目（B53901）が飛んでテストが落ちた。
    target = page.evaluate("""async () => {
      const views = [["経営","前期"],["会計","前期"],["短期大学部","前期"],
                     ["経営","後期"],["会計","後期"],["短期大学部","後期"]];
      for (const [department, term] of views) {
        currentDepartment = department; currentTerm = term;
        await renderTimetable();
        const cells = [...document.querySelectorAll("#timetable-grid td")];
        const empty = cells.filter((td) => !td.querySelector(".card"))
                           .map((td) => td.dataset.slot);
        const lone = cells.filter((td) => td.querySelectorAll(".card").length === 1)
                          .map((td) => td.querySelector(".card"));
        for (const card of lone) {
          for (const slot of empty) {
            const body = await api.moveSubject(
              window.appState.sessionId, card.dataset.code, [slot]);
            if (body.applied) {
              // 探索の副作用を残さない。見つけた 1 手は画面から改めて行う。
              await api.moveSubject(
                window.appState.sessionId, card.dataset.code, [card.dataset.grabbed]);
              return { code: card.dataset.code, from: card.dataset.grabbed, to: slot };
            }
          }
        }
      }
      return null;
    }""")
    assert target, "動かせるカードが 1 枚も無い結果だった"
    # 探索でサーバから取り直した状態に画面を合わせる（リロードすると
    # 読込タブへ戻ってしまうので、再描画だけ行う）
    page.evaluate("() => renderTimetable()")
    expect(page.locator("#timetable-grid .card").first).to_be_visible()

    code, origin = target["code"], target["from"]
    with page.expect_response(re.compile(r"/api/result/.+/move")) as response:
        page.locator(f'#timetable-grid .card[data-code="{code}"]').first.drag_to(
            page.locator(f'#timetable-grid td[data-slot="{target["to"]}"]')
        )
    assert response.value.json()["applied"] is True

    expect(
        page.locator(f'#timetable-grid .card[data-code="{code}"]').first
    ).to_have_attribute("data-grabbed", target["to"])

    expect(page.locator("#undo-button")).to_be_enabled()
    with page.expect_request(re.compile(r"/api/result/.+/(move|unplace)")):
        page.locator("#undo-button").click()

    expect(
        page.locator(f'#timetable-grid .card[data-code="{code}"]').first
    ).to_have_attribute("data-grabbed", origin)


def test_the_teacher_view_gathers_one_teacher_across_departments(
    page: Page, live_server, sample_xlsx
):
    """H1・H5・H6・H7 は教員単位で効くのに、学科別しか見られないと
    違反の理由が追えない。実データでは 82 名中 56 名が 3 学科にまたがる。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)

    page.locator('.view-tab[data-view-mode="teacher"]').click()
    expect(page.locator("#teacher-panel")).to_be_visible()
    expect(page.locator("#teacher-panel .teacher-name")).not_to_be_empty()
    expect(page.locator("#teacher-select")).to_be_visible()

    # 教員別のカードは担当が固定されているので、教員名ではなく学科を出す。
    teacher = page.locator("#teacher-panel .teacher-name").inner_text().strip()
    meta = page.locator("#timetable-grid .card .card-meta").first.inner_text()
    assert teacher not in meta
    assert any(name in meta for name in ("経営", "会計", "短期大学部"))
