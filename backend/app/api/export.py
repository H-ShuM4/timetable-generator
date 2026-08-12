"""生成結果を Excel ファイルとして返す。"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.export.excel_writer import write_timetable_excel
from app.session_store import store

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/{session_id}")
async def export_excel(session_id: str) -> FileResponse:
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    directory = Path(tempfile.mkdtemp())
    path = write_timetable_excel(data.context, data.result, directory / "時間割.xlsx")
    return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename="時間割.xlsx")
