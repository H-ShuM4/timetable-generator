"""生成結果を Excel ファイルとして返す。"""
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.export.excel_writer import write_timetable_excel
from app.session_store import store

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

DEFAULT_NAME = "時間割"
MAX_NAME_LENGTH = 80
"""ファイル名の上限。拡張子と保存先のパスを足しても Windows の 260 文字に
収まるだけの余裕を残す。"""

_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
"""Windows がファイル名に使えない文字。"""

_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}
"""Windows の予約名。この名前のファイルは作れない。"""


def safe_filename(raw: str | None) -> str:
    """事務局が入力した名前を、保存できる形に整える。

    **拡張子は付けない。** 呼ぶ側が付ける。

    落とすもの。

      ・`\\ / : * ? " < > |` … Windows がファイル名に使えない
      ・制御文字 … 改行が混じると Content-Disposition が壊れる。
        Starlette は非 ASCII を百分率符号化するのでヘッダ注入にはならないが、
        そもそも名前に入れる理由が無い
      ・前後の空白と末尾のドット … Windows が黙って落とすため、
        こちらで落としておかないと「入力した名前と違う」ことになる

    予約名（CON・NUL など）はそのままでは保存できないので既定へ戻す。
    空になった場合も既定へ戻す。**入力を拒まず、必ず何かを返す。**
    出力の直前に名前で弾かれると、生成し直しになりかねない。
    """
    text = unicodedata.normalize("NFC", str(raw or ""))
    text = "".join(c for c in text if unicodedata.category(c)[0] != "C")
    text = _FORBIDDEN.sub("", text).strip().rstrip(".")
    text = text[:MAX_NAME_LENGTH].strip()

    if not text or text.upper() in _RESERVED:
        return DEFAULT_NAME
    return text


@router.get("/{session_id}")
async def export_excel(
    session_id: str,
    name: str = Query(default=DEFAULT_NAME, description="保存するファイル名（拡張子なし）"),
) -> FileResponse:
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    filename = f"{safe_filename(name)}.xlsx"

    # 書き出しのたびに作る一時ディレクトリは、応答を送り終えてから消す。
    # 消さないと Excel 出力の回数だけゴミが残る。BackgroundTask は本文の
    # 送出後に走るので、ダウンロード自体には影響しない。
    directory = Path(tempfile.mkdtemp())
    path = write_timetable_excel(data.context, data.result, directory / filename)
    return FileResponse(
        path,
        media_type=XLSX_MEDIA_TYPE,
        filename=filename,
        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
    )
