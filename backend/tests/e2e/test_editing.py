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
    # **1 コマに 1 枚しか無いカードを選ぶ。** 16 枚が重なるコマもあり、
    # ドラッグの当たり判定は目当てのカードではなく手前の 1 枚を掴む。
    # 実際それで別の科目（B53901）が飛んでテストが落ちた。
    #
    # **掴む位置と落とす位置が縦に近いものを選ぶ。** グリッドは内側で
    # スクロールし、高さ 1700px に対して見えているのは 480px ほどしかない。
    # 離れていると両方を同時に画面へ出せず、合成ドラッグが届かない
    # （実際に 火1→月5 で落ちた）。1 コマに 16 枚入る行もあるので、
    # 同じ限の行というだけでは足りず、実際の座標で測って選ぶ。
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
        const middle = (el) => {
          const r = el.getBoundingClientRect();
          return r.top + r.height / 2;
        };
        for (const card of lone) {
          // 縦に近い空きコマから試す。同時に画面へ出せる相手を先に見つける。
          const near = cells
            .filter((td) => !td.querySelector(".card"))
            .map((td) => ({ slot: td.dataset.slot,
                            gap: Math.abs(middle(td) - middle(card)) }))
            .filter((x) => x.gap < 300)
            .sort((a, b) => a.gap - b.gap);
          for (const { slot } of near) {
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


def test_an_unplaced_subject_can_be_placed_by_dragging(
    page: Page, live_server, sample_xlsx
):
    """未配置科目をグリッドへ落とすと、実際に配置される。

    自動配置できなかった科目に事務局が手出しする唯一の道（設計仕様 §8.2）。
    ここが黙って失敗すると、置けないうえに理由も出ないので、事務局は
    何が起きたのか確かめようがない。

    **実データのモック生成では未配置が 0 件になる。** 画面と同じ道
    （undo が使う unplace）で 1 件つくってから、元のコマへ戻す。前の
    瞬間までそこに居たコマなので、制約で断られることがない。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)
    warnings = []
    page.on("dialog", lambda dialog: (warnings.append(dialog.message), dialog.accept()))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    origin = page.evaluate("""async () => {
      const card = document.querySelector("#timetable-grid .card");
      const found = { code: card.dataset.code, slot: card.closest("td").dataset.slot };
      await api.unplaceSubject(window.appState.sessionId, found.code);
      await renderTimetable();
      return found;
    }""")

    source = page.locator(f'.unplaced-card[data-code="{origin["code"]}"]')
    expect(source).to_be_visible()
    target = page.locator(f'#timetable-grid td[data-slot="{origin["slot"]}"]')
    source.scroll_into_view_if_needed()
    target.scroll_into_view_if_needed()

    source.drag_to(target)

    expect(page.locator(f'#timetable-grid .card[data-code="{origin["code"]}"]')).to_be_visible()
    assert page.evaluate("() => resultData.unplaced.length") == 0
    assert warnings == [], f"配置できたのに警告が出た: {warnings}"
    assert errors == [], f"画面が例外を投げた: {errors}"
