"""生成結果を Excel ファイルとして返す。"""
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

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

    # 書き出しのたびに作る一時ディレクトリは、応答を送り終えてから消す。
    # 消さないと Excel 出力の回数だけゴミが残る。BackgroundTask は本文の
    # 送出後に走るので、ダウンロード自体には影響しない。
    directory = Path(tempfile.mkdtemp())
    path = write_timetable_excel(data.context, data.result, directory / "時間割.xlsx")
    return FileResponse(
        path,
        media_type=XLSX_MEDIA_TYPE,
        filename="時間割.xlsx",
        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
    )
