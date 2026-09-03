"""結果画面の見回し操作を実ブラウザで確かめる。

ここで見るのは「配線」である。タブも検索欄も innerHTML で作り直される
要素で、リスナは描き直すたびに付け替える必要がある。付け忘れても
表示は正しいままなので、DOM スタブでは気づけない。実際、未配置科目の
ドラッグはこの付け忘れで動いていなかった。
"""
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import generate_in_mock_mode

pytestmark = pytest.mark.e2e


def visible_codes(page: Page) -> list[str]:
    return page.evaluate(
        """() => [...document.querySelectorAll("#timetable-grid .card")]
                   .map((c) => c.dataset.code)"""
    )


def grid_html(page: Page) -> str:
    return page.evaluate("() => document.getElementById('timetable-grid').innerHTML")


def wait_for_new_grid(page: Page, before: str) -> None:
    """描き直しを待つ。

    **タブのハンドラは renderTimetable を await しない。** click が返った
    時点ではサーバへの往復が終わっておらず、前の学科の表がまだ出ている。
    待たずに読むと、何も起きていないのに通ってしまう（実際そうなった）。
    """
    page.wait_for_function(
        "(before) => document.getElementById('timetable-grid').innerHTML !== before",
        arg=before,
    )


def belongs_to(page: Page, *, department: str, term: str | None = None) -> bool:
    """出ているカードが残らず、その学科・学期のものか。"""
    return page.evaluate(
        """({ department, term }) => {
             const cards = [...document.querySelectorAll("#timetable-grid .card")];
             return cards.length > 0 && cards.every((card) => {
               const found = resultData.placements.find((p) => p.code === card.dataset.code);
               return found && found.department === department
                      && (!term || found.term === term);
             });
           }""",
        {"department": department, "term": term},
    )


def test_switching_department_and_term_changes_the_table(
    page: Page, live_server, sample_xlsx
):
    """学科・学期のタブが表を入れ替える。

    6 通りの見え方すべてが同じ 1 本の描画を通る。押しても何も起きない、
    あるいは前の学科が残ることが無いようにする。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)

    before = grid_html(page)
    page.locator('.dept-tab:text-is("会計")').click()
    wait_for_new_grid(page, before)
    assert visible_codes(page), "会計の科目が 1 件も出ていない"
    assert belongs_to(page, department="会計"), "別の学科のカードが混ざっている"

    before = grid_html(page)
    page.locator('.term-tab:text-is("後期")').click()
    wait_for_new_grid(page, before)
    assert visible_codes(page)
    assert belongs_to(page, department="会計", term="後期"), "前期のカードが残っている"

    # 押したタブが選択状態として見えること
    expect(page.locator('.dept-tab:text-is("会計")')).to_have_class("dept-tab active")
    expect(page.locator('.term-tab:text-is("後期")')).to_have_class("term-tab active")


def test_a_teacher_can_be_found_by_typing_part_of_the_name(
    page: Page, live_server, sample_xlsx
):
    """実データの教員は 82 名。プルダウンだけでは目当てまで延々スクロールする。

    打鍵では選択肢だけを差し替え、Enter で表を描き直す（600 枚を 1 文字
    ごとに描き直さないため）。この二段構えが配線されているかを見る。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)
    page.locator('.view-tab:text-is("教員別")').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#teacher-select option').length > 10"
    )

    everyone = page.locator("#teacher-select option").count()

    target = page.locator("#teacher-select option").first.inner_text().strip()
    page.locator("#teacher-search").fill(target[0])
    narrowed = page.locator("#teacher-select option").count()
    assert narrowed < everyone, "打鍵しても選択肢が絞られていない"

    # 打鍵だけでは表は変わらない。Enter で初めて描き直す。
    page.locator("#teacher-search").press("Enter")
    expect(page.locator("#teacher-panel")).to_be_visible()
    shown = page.locator("#teacher-select").input_value()
    assert page.locator("#teacher-panel").inner_text().find(shown) >= 0


def test_a_search_that_matches_nobody_leaves_nothing_to_choose(
    page: Page, live_server, sample_xlsx
):
    """該当が無いことは、選べる項目が無いことで伝わる（件数は出さない）。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)
    page.locator('.view-tab:text-is("教員別")').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#teacher-select option').length > 10"
    )

    page.locator("#teacher-search").fill("該当しない氏名")
    expect(page.locator("#teacher-select")).to_be_disabled()
    assert page.locator("#teacher-select option").count() == 0


def test_ctrl_z_undoes_a_move(page: Page, live_server, sample_xlsx):
    """Ctrl+Z はボタンと同じ取り消しを行う。

    キーは document に付いており、結果画面を開いているときだけ効く。
    ボタン側は別のテストが見ているので、ここは鍵盤の経路だけを見る。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)
    page.on("dialog", lambda dialog: dialog.accept())

    # 未配置をひとつ作り、置き直してから取り消す。取り消しの対象を
    # 自分で用意するほうが、実データの空きコマ探しより確実である。
    origin = page.evaluate("""async () => {
      const card = document.querySelector("#timetable-grid .card");
      const found = { code: card.dataset.code, slot: card.closest("td").dataset.slot };
      await api.unplaceSubject(window.appState.sessionId, found.code);
      await renderTimetable();
      return found;
    }""")
    source = page.locator(f'.unplaced-card[data-code="{origin["code"]}"]')
    target = page.locator(f'#timetable-grid td[data-slot="{origin["slot"]}"]')
    source.scroll_into_view_if_needed()
    target.scroll_into_view_if_needed()
    source.drag_to(target)
    expect(page.locator(f'#timetable-grid .card[data-code="{origin["code"]}"]')).to_be_visible()

    page.keyboard.press("Control+z")

    expect(page.locator(f'.unplaced-card[data-code="{origin["code"]}"]')).to_be_visible()
    assert page.evaluate("() => resultData.unplaced.length") == 1


def test_ctrl_z_does_nothing_outside_the_result_view(
    page: Page, live_server, sample_xlsx
):
    """読込・生成の画面で Ctrl+Z を押しても時間割は動かない。"""
    generate_in_mock_mode(page, live_server, sample_xlsx)
    before = page.evaluate("() => resultData.placements.length")

    page.locator('#tabs button[data-view="upload"]').click()
    page.keyboard.press("Control+z")

    page.locator('#tabs button[data-view="result"]').click()
    assert page.evaluate("() => resultData.placements.length") == before


def test_the_side_blocks_open_only_when_they_have_something_to_say(
    page: Page, live_server, sample_xlsx
):
    """開いた状態で置くのは、そこに見るものがあるときだけ。

    カードの見方は毎回要るので常に開く。未配置科目は 0 件なら畳む
    （空の見出しがスクロールを食うだけになる）。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)

    assert page.locator("#block-legend").get_attribute("open") is not None, \
        "カードの見方は最初から開いている"

    unplaced = page.evaluate("() => resultData.unplaced.length")
    opened = page.locator("#block-unplaced").get_attribute("open") is not None
    assert opened == (unplaced > 0), \
        f"未配置 {unplaced} 件に対して開閉が合っていない (open={opened})"

    # 踏襲モードでしか出ないブロックは、モックでは伏せたままにする
    expect(page.locator("#block-inherit-skipped")).to_be_hidden()
