"""Excel のアップロードと読み込みサマリ。"""
import collections
import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import SessionRef, UploadResponse, UploadSummary, WarningOut
from app.ingest.curriculum_reader import read_curriculum_rows
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.pair_linking import assign_pair_ids
from app.ingest.markitdown_fallback import read_curriculum_with_fallback
from app.ingest.teacher_reader import read_teachers
from app.ingest.validators import check_partial_slots, collect_warnings
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
    # 復元用にどのファイルを読んだかを控える。セッションは再起動や
    # ブラウザの再読み込みで消えるため、Excel を保存して読み直せるようにする。
    saved: dict[str, tuple] = {}
    try:
        curriculum_path = _read_or_400(
            FILE_LABELS["curriculum"], lambda: _persist(curriculum)
        )
        saved["curriculum"] = (curriculum_path, curriculum.filename or "")
        subjects = _read_or_400(
            FILE_LABELS["curriculum"],
            lambda: read_curriculum_with_fallback(curriculum_path, logger),
        )
        partial_slot_warnings = _read_or_400(
            FILE_LABELS["curriculum"],
            lambda: check_partial_slots(read_curriculum_rows(curriculum_path)),
        )
        teachers_path = _read_or_400(
            FILE_LABELS["teachers"], lambda: _persist(teachers)
        )
        saved["teachers"] = (teachers_path, teachers.filename or "")
        teacher_map = _read_or_400(
            FILE_LABELS["teachers"], lambda: read_teachers(teachers_path)
        )
        previous_entries = {}
        if previous_curriculum is not None:
            previous_path = _read_or_400(
                FILE_LABELS["previous_curriculum"], lambda: _persist(previous_curriculum)
            )
            saved["previous_curriculum"] = (previous_path, previous_curriculum.filename or "")
            previous_entries = _read_or_400(
                FILE_LABELS["previous_curriculum"],
                lambda: read_previous_timetable(previous_path),
            )
        previous_teacher_map = {}
        if previous_teachers is not None:
            previous_teachers_path = _read_or_400(
                FILE_LABELS["previous_teachers"], lambda: _persist(previous_teachers)
            )
            saved["previous_teachers"] = (previous_teachers_path, previous_teachers.filename or "")
            previous_teacher_map = _read_or_400(
                FILE_LABELS["previous_teachers"],
                lambda: read_teachers(previous_teachers_path),
            )
    finally:
        logger.close()

    joint_mismatches = assign_joint_ids(subjects)
    assign_pair_ids(subjects)
    warnings = collect_warnings(subjects, teacher_map, joint_mismatches) + partial_slot_warnings

    data = SessionData(
        subjects=subjects,
        teachers=teacher_map,
        warnings=warnings,
        previous_entries=previous_entries,
        previous_teachers=previous_teacher_map,
    )
    session_id = store.create(data, saved)

    return _describe_session(session_id, data)


def build_summary(data: SessionData) -> UploadSummary:
    return UploadSummary(
        subject_count=len(data.subjects),
        teacher_count=len(data.teachers),
        intensive_count=sum(1 for s in data.subjects if s.is_intensive),
        quarter_count=sum(1 for s in data.subjects if s.quarter is not None),
        by_department=dict(
            collections.Counter(s.department.value for s in data.subjects)
        ),
        by_category=dict(collections.Counter(s.category.value for s in data.subjects)),
        by_teacher_kind=dict(
            collections.Counter(t.kind.value for t in data.teachers.values())
        ),
        has_previous_year=bool(data.previous_entries),
    )


def _describe_session(session_id: str, data: SessionData) -> UploadResponse:
    return UploadResponse(
        session_id=session_id,
        summary=build_summary(data),
        warnings=[WarningOut(**dataclasses.asdict(w)) for w in data.warnings],
    )


@router.get("/sessions", response_model=list[SessionRef])
async def list_sessions() -> list[SessionRef]:
    """保存されているセッションの一覧。新しい順。"""
    return [SessionRef(**row) for row in store.list_sessions()]


@router.get("/sessions/{session_id}", response_model=UploadResponse)
async def get_session(session_id: str) -> UploadResponse:
    """保存した Excel を読み直してセッションを復元し、読み込みサマリを返す。"""
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return _describe_session(session_id, data)
