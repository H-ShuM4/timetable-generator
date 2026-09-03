"""生成の実行と、SSE によるログ配信。

生成は別スレッドで動かし、ログはロガーの購読キューを通して流す。
"""
import asyncio
import json
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import GenerateIn, RetargetItem
from app.gemini.client import RealGeminiClient, RotatingGeminiClient
from app.logging.session_logger import SessionLogger
from app.scheduler.gemini_stage import make_gemini_placer
from app.scheduler.objectives import Weights
from app.scheduler.repair import EFFORT_SECONDS
from app.scheduler.inherit import InheritPlan, detect_retarget_codes
from app.scheduler.pipeline import GenerationCancelled, GenerationMode, run_pipeline
from app.session_store import store
from app.settings_store import SettingsStore

router = APIRouter(prefix="/api", tags=["generate"])

POLL_SECONDS = 0.2
"""ログを取りに行く間隔。人が読む速さに対して十分細かい。"""

KEEPALIVE_SECONDS = 15.0
"""何も起きない間に送るコメント。間に挟まる機器に切られないため。"""

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

    logger = SessionLogger(session_id)
    cancel = threading.Event()

    mode, use_ai = _decide_engine(GenerationMode(payload.mode), payload, api_key, logger)
    placer = _build_gemini_placer(settings, api_key, cancel, logger) if use_ai else None
    inherit_plan = (
        _build_inherit_plan(data, payload) if mode is GenerationMode.INHERIT else None
    )

    data.logger = logger
    data.result = None
    data.error = None
    data.cancelled = False
    data.cancel_event = cancel
    data.running = True

    def worker() -> None:
        try:
            data.result = run_pipeline(
                data.subjects, data.teachers, mode, logger,
                gemini_placer=placer, inherit_plan=inherit_plan,
                weights=Weights.from_steps(payload.weights),
                repair_seconds=EFFORT_SECONDS.get(payload.repair_effort, 0.0),
                should_cancel=cancel.is_set,
            )
            store.save_result(session_id)
        except GenerationCancelled:
            # 事務局が自分で止めた。失敗ではないので error は立てない。
            data.cancelled = True
        except Exception as error:  # 生成を止めず、必ずログに残す
            data.error = str(error)
            logger.error(f"生成中に予期しないエラーが発生しました: {error}", stage="Stage 6")
        finally:
            data.running = False
            data.cancel_event = None
            logger.close()

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started", "mode": mode.value}


def _decide_engine(
    mode: GenerationMode, payload: GenerateIn, api_key: str | None, logger: SessionLogger
) -> tuple[GenerationMode, bool]:
    """実際に使うモードと、Gemini に頼むかどうかを決め、その判断をログに残す。

    ここで黙って別のことをすると、事務局は結果を見ても気づけない。
    どちらへ倒したかを必ず 1 行書く。

    **踏襲モードは Gemini を要らない。** 前年度の配置をそのまま置くのは
    決定的な処理で、組み替え対象はソルバーが埋められる。以前はここで
    「MOCK 以外」をまとめて落としており、キーが無いだけで踏襲が捨てられ、
    inherit_plan が組まれないまま普通の生成になっていた。ログには
    「モックモードで実行します」としか出ないので、事務局は気づけない。

    **組み替えを誰に任せるかは事務局が決める。** キーがあるだけで Gemini
    に渡ると、数十分と無料枠を黙って使ってしまう。
    """
    if mode is GenerationMode.OPTIMIZE and not api_key:
        logger.warn("API キーが未設定のためモックモードで実行します", stage="Stage 0")
        mode = GenerationMode.MOCK

    wants_ai = mode is GenerationMode.OPTIMIZE or (
        mode is GenerationMode.INHERIT and payload.retarget_with == "ai"
    )
    if mode is GenerationMode.INHERIT:
        if not wants_ai:
            logger.info("組み替え対象はソルバーが配置します", stage="Stage 0")
        elif not api_key:
            logger.warn(
                "API キーが未設定のため、組み替え対象はソルバーが配置します",
                stage="Stage 0",
            )
        else:
            logger.info("組み替え対象は AI が配置します", stage="Stage 0")

    return mode, bool(wants_ai and api_key)


def _build_gemini_placer(
    settings, api_key: str, cancel: threading.Event, logger: SessionLogger
):
    """Gemini の配置係を組む。キーが不正ならここで弾く。

    走り出してから 400 が返ると、事務局は生成が始まったと思って待ち続ける。
    先頭のモデルを 1 つ作って、開始前に確かめる。
    """
    models = settings.models_in_order()

    def announce_switch(left: str, next_model: str | None, error: Exception) -> None:
        from app.gemini.client import ModelBusyError

        reason = "混み合っています" if isinstance(error, ModelBusyError) else "利用枠に達しました"
        destination = (
            f"{next_model} に切り替えます" if next_model
            else "切り替え先がもうありません"
        )
        logger.warn(f"{left} が{reason}。{destination}", stage="Gemini")

    try:
        gemini_client = RotatingGeminiClient(
            lambda model: RealGeminiClient(api_key, model),
            models,
            on_switch=announce_switch,
        )
        # RealGeminiClient は生成時に API キーを検証する。
        RealGeminiClient(api_key, models[0])
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "Gemini クライアントの初期化に失敗しました。"
                f"API キーが不正である可能性があります: {error}"
            ),
        ) from error

    if len(models) > 1:
        logger.info(
            f"モデルを {len(models)} 個使います（枠切れ時に順に切り替え）: "
            f"{'→'.join(models)}",
            stage="Stage 0",
        )
    return make_gemini_placer(
        gemini_client, settings.max_retries, should_cancel=lambda: cancel.is_set()
    )


def _build_inherit_plan(data, payload: GenerateIn) -> InheritPlan:
    """前年度をどこまで踏襲するかを決める。

    **空リスト（すべて解除）と未指定を取り違えない。** 前者は「1 件も
    組み替えない」、後者は「自動検出に任せる」である。以前は真偽値として
    見ていたため、事務局がチェックを全部外すと自動検出に化けていた。
    """
    retarget = (
        set(payload.retarget_codes)
        if payload.retarget_codes is not None
        else detect_retarget_codes(
            data.subjects, data.teachers,
            data.previous_entries, data.previous_teachers,
        )
    )
    return InheritPlan(data.previous_entries, retarget)

@router.post("/generate/{session_id}/cancel", status_code=202)
async def cancel_generation(session_id: str) -> dict:
    """走っている生成を中止する。

    AI モードは数十分かかる。止める手段が無いと、間違えて始めた生成が
    終わるまで事務局は何もできず、`running` が立ったままなので次の生成も
    409 で弾かれる。実際に止まるのは段の変わり目なので、押してすぐには
    終わらないことがある。
    """
    data = _require_session(session_id)
    if not data.running or data.cancel_event is None:
        raise HTTPException(status_code=409, detail="生成は実行されていません")

    data.cancel_event.set()
    if data.logger is not None:
        data.logger.warn("中止を受け付けました。区切りのよいところで止めます", stage="Stage 0")
    return {"status": "cancelling"}


@router.get("/generate/{session_id}/stream")
async def stream_logs(session_id: str) -> StreamingResponse:
    data = _require_session(session_id)
    if data.logger is None:
        raise HTTPException(status_code=409, detail="まだ生成が開始されていません")

    logger = data.logger
    backlog = logger.events
    stream = logger.subscribe()

    async def events():
        """ログを流し続ける。**同期のキュー待ちにしてはいけない。**

        以前は `queue.get()` で待っており、待っている間ワーカースレッドを
        1 本占有した。サーバを止めるときそのスレッドは中断できず、
        KeyboardInterrupt と CancelledError の長いトレースバックが
        ターミナルに出ていた。画面を閉じても待ち続けるため、購読者も
        溜まり続けた。

        待たずに取り出し、無ければ少し眠る。スレッドを 1 本も使わず、
        中断にも即座に応じられる。
        """
        try:
            for event in backlog:
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
            idle = 0.0
            while True:
                try:
                    event = stream.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(POLL_SECONDS)
                    idle += POLL_SECONDS
                    if idle >= KEEPALIVE_SECONDS:
                        idle = 0.0
                        yield ": keep-alive\n\n"
                    continue
                idle = 0.0
                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    return
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        finally:
            logger.unsubscribe(stream)

    return StreamingResponse(events(), media_type="text/event-stream")
