"""E2E から使う共通の道順。

読込 → モック生成 → 結果 までは、どのテストも同じところを通る。
**AI モードを選んではいけない。** Gemini の無料枠を消費し数十分かかる。
"""
import re

from playwright.sync_api import Page, expect

ACTIVE = re.compile(r"\bactive\b")

GENERATION_TIMEOUT_MS = 180_000
"""モック生成の待ち。ソルバの見直し時間を含めても十分な上限。"""


def load_workbooks(page: Page, live_server: str, sample_xlsx) -> None:
    page.goto(live_server)
    page.locator("#file-input").set_input_files(sample_xlsx)
    expect(page.locator("#upload-button")).to_be_enabled()
    page.locator("#upload-button").click()
    expect(page.locator('#tabs button[data-view="generate"]')).to_be_enabled()


def generate_in_mock_mode(page: Page, live_server: str, sample_xlsx) -> None:
    load_workbooks(page, live_server, sample_xlsx)
    page.locator('#tabs button[data-view="generate"]').click()
    expect(page.locator('input[name="mode"][value="mock"]')).to_be_checked()
    page.locator("#generate-button").click()
    expect(page.locator("#view-result")).to_have_class(
        ACTIVE, timeout=GENERATION_TIMEOUT_MS
    )
    expect(page.locator("#timetable-grid .card").first).to_be_visible()
