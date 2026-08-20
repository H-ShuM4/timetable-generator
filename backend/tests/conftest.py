"""実データを読む重いフィクスチャ。セッション内で 1 度だけ読み込む。"""
from pathlib import Path

import pytest

from app.constraints.context import Context
from app.ingest.curriculum_reader import read_curriculum
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.teacher_reader import read_teachers

_ROOT = Path(__file__).resolve().parents[2]
CURRICULUM_XLSX = _ROOT / "カリキュラム一覧(整形済み).xlsx"
TEACHERS_XLSX = _ROOT / "教員一覧(整形済み).xlsx"


@pytest.fixture(scope="session")
def real_context() -> Context:
    subjects = read_curriculum(CURRICULUM_XLSX)
    assign_joint_ids(subjects)
    return Context.from_lists(subjects, read_teachers(TEACHERS_XLSX))


@pytest.fixture(scope="session")
def real_gemini_codes(real_context) -> list[str]:
    """Gemini に投げる対象。曜日時限が確定済みの科目と集中講義は除く。"""
    return [
        subject.code
        for subject in real_context.subjects.values()
        if not subject.fixed_slot and not subject.is_intensive
    ]
