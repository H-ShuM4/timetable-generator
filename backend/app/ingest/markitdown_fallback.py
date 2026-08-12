"""想定外の列構成をした Excel が投入されたときの経路。

MarkItDown で Markdown 化して中身をログに残し、処理は止める。
黙って誤読するより、事務局に形式の違いを見せる方が安全と判断した。
"""
from pathlib import Path

import openpyxl

from app.ingest.curriculum_reader import read_curriculum
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject

REQUIRED_COLUMNS = frozenset({
    "授業コード", "授業科目名称", "学科", "年次配当", "開講期間", "科目区分", "教員氏名",
})

MARKDOWN_PREVIEW_CHARS = 2000


def has_expected_columns(path: str | Path) -> bool:
    """いずれかのシートが必須列をすべて備えているか。"""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
                headers = {str(v).strip() for v in row if v is not None}
                if REQUIRED_COLUMNS <= headers:
                    return True
        return False
    finally:
        workbook.close()


def convert_to_markdown(path: str | Path) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(str(path)).text_content


def read_curriculum_with_fallback(
    path: str | Path, logger: SessionLogger
) -> list[Subject]:
    if has_expected_columns(path):
        return read_curriculum(path)

    logger.error(
        f"想定外の列構成の Excel です: {Path(path).name}。"
        f"必須列: {'、'.join(sorted(REQUIRED_COLUMNS))}",
        stage="Stage 0",
    )
    try:
        preview = convert_to_markdown(path)[:MARKDOWN_PREVIEW_CHARS]
        logger.info(f"MarkItDown による内容プレビュー:\n{preview}", stage="Stage 0")
    except Exception as error:
        logger.error(f"MarkItDown での変換にも失敗しました: {error}", stage="Stage 0")

    raise ValueError(f"想定外の列構成の Excel です: {Path(path).name}")
