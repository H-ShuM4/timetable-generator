"""Excel のアップロードと読み込みサマリ。"""
import collections
import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import SessionRef, UploadResponse, UploadSummary, WarningOut
from app.ingest.session_builder import load_session_data
from app.logging.session_logger import SessionLogger
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
    uploads = {
        "curriculum": curriculum,
        "teachers": teachers,
        "previous_curriculum": previous_curriculum,
        "previous_teachers": previous_teachers,
    }
    # 控えた一時ファイルは、複写が済んだら消す。ここで残すと 1 アップロード
    # につき最大 4 件が積み上がり、事務局 PC で長く使うほど一時領域を食う。
    # 途中の読み取り失敗で 400 を返す経路でも消えるよう、逐次控えて finally
    # でまとめて片付ける。
    saved: dict[str, tuple[Path, str]] = {}
    try:
        for role, uploaded in uploads.items():
            if uploaded is None:
                continue
            path = _read_or_400(FILE_LABELS[role], lambda u=uploaded: _persist(u))
            saved[role] = (path, uploaded.filename or "")

        loaded = load_session_data(
            saved["curriculum"][0],
            saved["teachers"][0],
            logger,
            previous_curriculum=saved.get("previous_curriculum", (None,))[0],
            previous_teachers=saved.get("previous_teachers", (None,))[0],
            read=lambda role, action: _read_or_400(FILE_LABELS[role], action),
        )

        data = SessionData(
            subjects=loaded.subjects,
            teachers=loaded.teachers,
            warnings=loaded.warnings,
            previous_entries=loaded.previous_entries,
            previous_teachers=loaded.previous_teachers,
        )
        session_id = store.create(data, saved)
    finally:
        logger.close()
        for path, _ in saved.values():
            path.unlink(missing_ok=True)

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
        has_previous_teachers=bool(data.previous_teachers),
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
