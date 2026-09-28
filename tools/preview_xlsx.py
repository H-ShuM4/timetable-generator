#!/usr/bin/env python3
"""xlsx のシートを HTML に起こし、Chromium で撮って目視する。

Excel 出力の見た目を確かめるための道具。開発機に LibreOffice が無くても、
E2E で入れてある Chromium があれば使える。罫線の太さ・種類、塗り、結合、
列幅・行高、フォントの大きさを写すので、Excel で開いたときの見え方を
おおむね確かめられる。

    python3 tools/preview_xlsx.py <book.xlsx> <シート名> <出力.png> [最大行] [開始行]

見出し（1〜3 行目）は開始行を指定しても必ず付ける。どの列が何かを
見失わないため。

**完全一致ではない。** とくに shrink_to_fit（幅に合わせて文字を縮める）は
再現していないので、長い科目名は隣の列へはみ出して見える。Excel では
縮んで収まる。折り返しの有無だけは正しく写るので、そこは信用してよい。

**backend/ の下に置いていない。** make-dist.sh は backend/app と
backend/config を丸ごと配布物へ入れるため、そこへ置くと事務局に開発用の
道具まで配ってしまう。
"""
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

BORDER = {
    "medium": "2px solid #000", "thick": "3px solid #000",
    "thin": "1px solid #000", "hair": "1px solid #999",
    "dotted": "1px dotted #666", "dashed": "1px dashed #666",
    "double": "3px double #000",
}


def side(value):
    return BORDER.get(value.style, "none") if value and value.style else "none"


def colour(fill):
    if fill is None or fill.patternType != "solid":
        return None
    c = fill.fgColor
    if c.type == "rgb" and c.rgb and c.rgb not in ("00000000",):
        return "#" + str(c.rgb)[-6:]
    if c.type == "theme":
        # theme0 は白。tint が負なら暗くする（見本の見出しの灰色）。
        level = max(0, min(255, round(255 * (1 + (c.tint or 0)))))
        return f"rgb({level},{level},{level})" if c.theme == 0 else "#eee"
    return "#ddd"


def render(path: Path, title: str, out: Path, limit: int, start: int = 1) -> None:
    ws = load_workbook(path)[title]
    rows = min(ws.max_row, limit)
    cols = ws.max_column

    skip = set()
    span = {}
    for rng in ws.merged_cells.ranges:
        span[(rng.min_row, rng.min_col)] = (
            rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    skip.add((r, c))

    widths = []
    for c in range(1, cols + 1):
        dim = ws.column_dimensions.get(get_column_letter(c))
        widths.append(round((dim.width if dim and dim.width else 8.4) * 7 + 5))

    html = ["<!doctype html><meta charset='utf-8'><style>",
            "body{margin:0;background:#fff;font-family:'Noto Sans CJK JP',sans-serif}",
            "table{border-collapse:collapse;table-layout:fixed}",
            "td{overflow:hidden;padding:0 2px;vertical-align:middle}",
            "</style><table><colgroup>"]
    html += [f"<col style='width:{w}px'>" for w in widths]
    html.append("</colgroup>")

    wanted = list(range(1, 4)) + [r for r in range(max(start, 4), rows + 1)]
    for r in wanted:
        dim = ws.row_dimensions.get(r)
        height = round((dim.height if dim and dim.height else 15) * 4 / 3)
        html.append(f"<tr style='height:{height}px'>")
        for c in range(1, cols + 1):
            if (r, c) in skip:
                continue
            cell = ws.cell(r, c)
            b = cell.border
            style = [f"border-left:{side(b.left)}", f"border-right:{side(b.right)}",
                     f"border-top:{side(b.top)}", f"border-bottom:{side(b.bottom)}"]
            back = colour(cell.fill)
            if back:
                style.append(f"background:{back}")
            font = cell.font
            if font and font.size:
                style.append(f"font-size:{round(font.size * 4 / 3)}px")
            if font and font.bold:
                style.append("font-weight:700")
            align = cell.alignment
            style.append(f"text-align:{align.horizontal or 'left'}")
            if align.wrap_text:
                style.append("white-space:pre-wrap")
            else:
                style.append("white-space:nowrap")
            rowspan, colspan = span.get((r, c), (1, 1))
            attrs = "".join(f" {k}='{v}'" for k, v in
                            (("rowspan", rowspan), ("colspan", colspan)) if v > 1)
            text = "" if cell.value is None else str(cell.value)
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
            html.append(f"<td{attrs} style=\"{';'.join(style)}\">{text}</td>")
        html.append("</tr>")
    html.append("</table>")

    page = out.with_suffix(".html")
    page.write_text("".join(html), encoding="utf-8")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        tab = browser.new_page(viewport={"width": sum(widths) + 40, "height": 1200})
        tab.goto(page.as_uri())
        tab.locator("table").screenshot(path=str(out))
        browser.close()
    print(f"{out}  ({rows} 行 × {cols} 列)")


if __name__ == "__main__":
    book, sheet, target = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    render(Path(book), sheet, target,
           int(sys.argv[4]) if len(sys.argv) > 4 else 60,
           int(sys.argv[5]) if len(sys.argv) > 5 else 1)
