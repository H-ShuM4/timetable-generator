"""ログパネルと、開き直したときの復元を実ブラウザで確かめる。

ログは SSE で流れてくる。EventSource は DOM スタブでは動かないので、
実際に生成を走らせて届いたものを見るしかない。復元も localStorage と
サーバの往復が噛み合って初めて成り立つ。
"""
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import generate_in_mock_mode

pytestmark = pytest.mark.e2e

COLLAPSED = re.compile(r"\bcollapsed\b")

LEVELS_SHOWN = """() => [...new Set([...document.querySelectorAll("#log-body > div")]
                        .map((n) => n.className))]"""


def lines(page: Page) -> int:
    return page.locator("#log-body > div").count()


def test_the_log_fills_up_and_folds_away_when_the_work_is_done(
    page: Page, live_server, sample_xlsx
):
    """生成中の進み具合はログでしか分からない。終わったら畳んで場所を譲る。

    畳むのは意図した動き。結果を見る段になっても 613 件ぶんのログが
    画面の下半分を占めていては邪魔になる。読み返したくなったときは
    自分で開ける。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)

    assert lines(page) > 0, "生成したのにログが 1 行も届いていない"
    expect(page.locator("#log-panel")).to_have_class(COLLAPSED)
    expect(page.locator("#log-toggle")).to_have_text("▲")

    page.locator("#log-toggle").click()
    expect(page.locator("#log-panel")).not_to_have_class(COLLAPSED)
    expect(page.locator("#log-toggle")).to_have_text("▼")

    page.locator("#log-toggle").click()
    expect(page.locator("#log-panel")).to_have_class(COLLAPSED)


def test_the_log_can_be_narrowed_to_one_level(page: Page, live_server, sample_xlsx):
    """うまくいかなかったときに、その段だけを拾えるようにする。

    モックが素直に通ったときは ERROR が 1 行も出ない。**行数が減ったか
    ではなく、残った行がその段だけかを見る**（0 行になるのも正しい姿）。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)

    everything = lines(page)
    assert everything > 0
    assert "log-INFO" in page.evaluate(LEVELS_SHOWN)

    page.locator("#log-filter").select_option("ERROR")
    assert page.evaluate(LEVELS_SHOWN) in ([], ["log-ERROR"]), "ERROR 以外が残っている"

    page.locator("#log-filter").select_option("INFO")
    assert page.evaluate(LEVELS_SHOWN) == ["log-INFO"], "INFO 以外が残っている"
    assert lines(page) <= everything

    page.locator("#log-filter").select_option("ALL")
    assert lines(page) == everything, "すべてへ戻しても行数が戻らない"


def test_the_last_session_comes_back_after_closing_the_browser(
    page: Page, live_server, sample_xlsx
):
    """ブラウザを閉じても、読み込んだデータと作った時間割は残る。

    事務局は時間割づくりを何日かに分ける。開き直すたびに Excel から
    やり直しでは使いものにならない。
    """
    generate_in_mock_mode(page, live_server, sample_xlsx)
    before = page.evaluate("() => window.appState.sessionId")
    placements = page.evaluate("() => resultData.placements.length")

    page.reload()

    expect(page.locator("#upload-summary")).to_contain_text("復元しました")
    assert page.evaluate("() => window.appState.sessionId") == before
    expect(page.locator('#tabs button[data-view="result"]')).to_be_enabled()

    page.locator('#tabs button[data-view="result"]').click()
    expect(page.locator("#timetable-grid .card").first).to_be_visible()
    assert page.evaluate("() => resultData.placements.length") == placements
