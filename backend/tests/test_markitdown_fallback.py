from pathlib import Path

import openpyxl
import pytest

from app.ingest.markitdown_fallback import (
    REQUIRED_COLUMNS,
    convert_to_markdown,
    has_expected_columns,
    read_curriculum_with_fallback,
)
from app.logging.session_logger import SessionLogger

from tests.conftest import CURRICULUM_XLSX  # noqa: E402


def _write_broken_workbook(path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["適当な列", "別の列"])
    sheet.append(["値1", "値2"])
    workbook.save(path)
    return path


def test_required_columns_are_declared():
    assert {"授業コード", "授業科目名称", "学科", "科目区分"} <= REQUIRED_COLUMNS


def test_real_workbook_has_expected_columns():
    assert has_expected_columns(CURRICULUM_XLSX) is True


def test_broken_workbook_lacks_expected_columns(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    assert has_expected_columns(path) is False


def test_fallback_reads_normal_workbook(tmp_path):
    logger = SessionLogger("m1", log_dir=tmp_path)
    subjects = read_curriculum_with_fallback(CURRICULUM_XLSX, logger)
    assert len(subjects) == 658
    logger.close()


def test_fallback_raises_and_logs_for_broken_workbook(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    logger = SessionLogger("m2", log_dir=tmp_path)

    with pytest.raises(ValueError, match="想定外"):
        read_curriculum_with_fallback(path, logger)

    assert any(e.level == "ERROR" for e in logger.events)
    logger.close()


def test_unreadable_file_is_rejected_with_a_log(tmp_path):
    # 「間違ったファイルを投入した」場面。落ちずに内容を見せて止める
    path = tmp_path / "garbage.xlsx"
    path.write_bytes(b"this is not a workbook")
    logger = SessionLogger("m3", log_dir=tmp_path)

    assert has_expected_columns(path) is False
    with pytest.raises(ValueError, match="想定外"):
        read_curriculum_with_fallback(path, logger)

    assert any(e.level == "ERROR" for e in logger.events)
    logger.close()


def test_convert_to_markdown_returns_text(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    markdown = convert_to_markdown(path)
    assert isinstance(markdown, str)
    assert "値1" in markdown
