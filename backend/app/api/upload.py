"""Excel のアップロードと読み込みサマリ。"""
import collections
import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import UploadResponse, UploadSummary, WarningOut
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.markitdown_fallback import read_curriculum_with_fallback
from app.ingest.teacher_reader import read_teachers
from app.ingest.validators import collect_warnings
from app.logging.session_logger import SessionLogger
from app.scheduler.inherit import read_previous_timetable
from app.session_store import SessionData, store

router = APIRouter(prefix="/api", tags=["upload"])

FILE_LABELS = {
    "curriculum": "カリキュラム一覧",
    "teachers": "教員一覧",
    "previous_curriculum": "前年度の時間割",
    "previous_teachers": "前年度の教員一覧",
}


def _read_or_400(label: str, read):
    """読み取り失敗を、どのファイルが原因か分かる 400 に変換する。

    事務局は最大 4 種類のファイルを一度に投入するため、どれが問題なのか
    を示さないと直しようがない。スタックトレースを返してはならない。
    """
    try:
        return read()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"{label}を読み取れませんでした: {error}",
        ) from error


def _persist(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.xlsx").suffix or ".xlsx"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.write(upload.file.read())
    handle.close()
    return Path(handle.name)


@router.post("/upload", response_model=UploadResponse)
async def upload(
    curriculum: UploadFile = File(...),
    teachers: UploadFile = File(...),
    previous_curriculum: UploadFile | None = File(None),
    previous_teachers: UploadFile | None = File(None),
) -> UploadResponse:
    logger = SessionLogger("upload")
    try:
        subjects = _read_or_400(
            FILE_LABELS["curriculum"],
            lambda: read_curriculum_with_fallback(_persist(curriculum), logger),
        )
        teacher_map = _read_or_400(
            FILE_LABELS["teachers"],
            lambda: read_teachers(_persist(teachers)),
        )
        previous_entries = {}
        if previous_curriculum is not None:
            previous_entries = _read_or_400(
                FILE_LABELS["previous_curriculum"],
                lambda: read_previous_timetable(_persist(previous_curriculum)),
            )
        previous_teacher_map = {}
        if previous_teachers is not None:
            previous_teacher_map = _read_or_400(
                FILE_LABELS["previous_teachers"],
                lambda: read_teachers(_persist(previous_teachers)),
            )
    finally:
        logger.close()

    joint_mismatches = assign_joint_ids(subjects)
    warnings = collect_warnings(subjects, teacher_map, joint_mismatches)

    data = SessionData(
        subjects=subjects,
        teachers=teacher_map,
        warnings=warnings,
        previous_entries=previous_entries,
        previous_teachers=previous_teacher_map,
    )
    session_id = store.create(data)

    summary = UploadSummary(
        subject_count=len(subjects),
        teacher_count=len(teacher_map),
        intensive_count=sum(1 for s in subjects if s.is_intensive),
        quarter_count=sum(1 for s in subjects if s.quarter is not None),
        by_department=dict(
            collections.Counter(s.department.value for s in subjects)
        ),
        by_category=dict(collections.Counter(s.category.value for s in subjects)),
        by_teacher_kind=dict(
            collections.Counter(t.kind.value for t in teacher_map.values())
        ),
        has_previous_year=bool(previous_entries),
    )
    return UploadResponse(
        session_id=session_id,
        summary=summary,
        warnings=[WarningOut(**dataclasses.asdict(w)) for w in warnings],
    )
