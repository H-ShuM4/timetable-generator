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
        subjects = read_curriculum_with_fallback(_persist(curriculum), logger)
    except ValueError as error:
        logger.close()
        raise HTTPException(status_code=400, detail=str(error)) from error

    teacher_map = read_teachers(_persist(teachers))
    joint_mismatches = assign_joint_ids(subjects)
    warnings = collect_warnings(subjects, teacher_map, joint_mismatches)

    previous_entries = {}
    previous_teacher_map = {}
    if previous_curriculum is not None:
        previous_entries = read_previous_timetable(_persist(previous_curriculum))
    if previous_teachers is not None:
        previous_teacher_map = read_teachers(_persist(previous_teachers))
    logger.close()

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
