"""生成の実行と、SSE によるログ配信。

生成は別スレッドで動かし、ログはロガーの購読キューを通して流す。
"""
import json
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import GenerateIn, RetargetItem
from app.gemini.client import RealGeminiClient
from app.logging.session_logger import SessionLogger
from app.scheduler.gemini_stage import make_gemini_placer
from app.scheduler.inherit import InheritPlan, detect_retarget_codes
from app.scheduler.pipeline import GenerationMode, run_pipeline
from app.session_store import store
from app.settings_store import SettingsStore

router = APIRouter(prefix="/api", tags=["generate"])

settings_store = SettingsStore()


def _require_session(session_id: str):
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return data


@router.get("/retarget/{session_id}", response_model=list[RetargetItem])
async def get_retarget(session_id: str) -> list[RetargetItem]:
    data = _require_session(session_id)
    codes = detect_retarget_codes(
        data.subjects, data.teachers, data.previous_entries, data.previous_teachers
    )
    items: list[RetargetItem] = []
    for subject in data.subjects:
        if subject.code not in codes:
            continue
        teacher = data.teachers.get(subject.teacher)
        if teacher is not None and teacher.kind.value in ("非常勤", "特任"):
            reason = f"非専任（{teacher.kind.value}）"
        elif subject.code not in data.previous_entries:
            reason = "前年度に存在しない新規科目"
        elif data.previous_entries[subject.code].teacher != subject.teacher:
            reason = "担当教員の変更"
        else:
            reason = "研究日の変更"
        items.append(RetargetItem(
            code=subject.code, name=subject.name, teacher=subject.teacher, reason=reason
        ))
    return items


@router.post("/generate/{session_id}", status_code=202)
async def start_generation(session_id: str, payload: GenerateIn) -> dict:
    data = _require_session(session_id)
    if data.running:
        raise HTTPException(status_code=409, detail="生成が既に実行中です")

    settings = settings_store.load()
    api_key = settings_store.get_api_key()
    mode = GenerationMode(payload.mode)

    logger = SessionLogger(session_id)
    if mode is not GenerationMode.MOCK and not api_key:
        logger.warn("API キーが未設定のためモックモードで実行します", stage="Stage 0")
        mode = GenerationMode.MOCK

    placer = None
    if mode is not GenerationMode.MOCK:
        placer = make_gemini_placer(
            RealGeminiClient(api_key, settings.model), settings.max_retries
        )

    inherit_plan = None
    if mode is GenerationMode.INHERIT:
        retarget = set(payload.retarget_codes) or detect_retarget_codes(
            data.subjects, data.teachers, data.previous_entries, data.previous_teachers
        )
        inherit_plan = InheritPlan(data.previous_entries, retarget)

    data.logger = logger
    data.result = None
    data.running = True

    def worker() -> None:
        try:
            data.result = run_pipeline(
                data.subjects, data.teachers, mode, logger,
                gemini_placer=placer, inherit_plan=inherit_plan,
            )
            store.save_result(session_id)
        except Exception as error:  # 生成を止めず、必ずログに残す
            logger.error(f"生成中に予期しないエラーが発生しました: {error}", stage="Stage 6")
        finally:
            data.running = False
            logger.close()

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started", "mode": mode.value}


@router.get("/generate/{session_id}/stream")
async def stream_logs(session_id: str) -> StreamingResponse:
    data = _require_session(session_id)
    if data.logger is None:
        raise HTTPException(status_code=409, detail="まだ生成が開始されていません")

    logger = data.logger
    backlog = logger.events
    queue = logger.subscribe()

    def events():
        for event in backlog:
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        while True:
            event = queue.get()
            if event is None:
                yield "event: done\ndata: {}\n\n"
                return
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
