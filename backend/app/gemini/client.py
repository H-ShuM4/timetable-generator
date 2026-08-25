"""Gemini API クライアント。

失敗はすべて GeminiError に包む。呼び出し側は再試行するだけでよく、
SDK の例外型に依存しない。
"""
from typing import Protocol

from app.gemini.prompts import RESPONSE_SCHEMA


class GeminiError(Exception):
    """Gemini 呼び出しに関するあらゆる失敗。"""


class QuotaExceededError(GeminiError):
    """そのモデルの利用枠を使い切った。

    無料枠は 1 モデルあたり 1 日単位で決まっているため、待っても回復
    しない。呼び出し側は再試行ではなく別モデルへの切り替えで対処する。
    """


class ModelBusyError(GeminiError):
    """モデルが混み合っていて応じられない（503）。

    枠切れと違い時間が経てば回復するが、その場で待つには長すぎる。
    呼び出し側は枠切れと同じく次のモデルへ移る。
    """


QUOTA_MARKERS = ("RESOURCE_EXHAUSTED", "quota", "rate limit")
"""利用枠切れと判断する語。SDK の例外型に依存しないため文字列で見る。"""

BUSY_MARKERS = ("UNAVAILABLE", "high demand", "overloaded")
"""モデルが混雑していると判断する語。"""

REQUEST_TIMEOUT_SECONDS = 90
"""1 回の呼び出しを待つ上限。

実測で 503 が返るまで 2 分 25 秒待たされたことがある。混雑している
モデルを待ち続けるより、切り上げて次のモデルへ移るほうが早い。
"""


def _has_status(error: Exception, code: int) -> bool:
    return any(getattr(error, name, None) == code for name in ("code", "status_code"))


def is_quota_error(error: Exception) -> bool:
    """例外が利用枠切れかどうか。判定を誤ってもソルバーへ落ちるだけで済む。"""
    if _has_status(error, 429):
        return True
    text = str(error).lower()
    return any(marker.lower() in text for marker in QUOTA_MARKERS)


def is_busy_error(error: Exception) -> bool:
    """モデルが混み合っていて応じられない状態か（503）。

    枠切れとは別物だが、対処は同じで「次のモデルへ移る」でよい。同じ
    モデルに送り直しても、混雑は数秒では解消しない。実際、1 回の呼び出しに
    2 分 25 秒かかったうえで 503 が返り、そのまま同じモデルへ再送していた。
    """
    if _has_status(error, 503):
        return True
    text = str(error).lower()
    return any(marker.lower() in text for marker in BUSY_MARKERS)


class GeminiClient(Protocol):
    def generate(self, prompt: str) -> str:
        """プロンプトを送り、応答テキストを返す。"""


class RealGeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import types

        # 待ち時間に上限を置く。混雑したモデルを何分も待つより、
        # 打ち切って次のモデルへ移るほうが速い。
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
        )
        self._model = model

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                },
            )
        except Exception as error:  # SDK の例外型に依存しない
            if is_quota_error(error):
                raise QuotaExceededError(str(error)) from error
            if is_busy_error(error):
                raise ModelBusyError(str(error)) from error
            raise GeminiError(str(error)) from error

        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("空の応答が返りました")
        return text


class RotatingGeminiClient:
    """複数モデルを順に使い、枠切れのたびに次のモデルへ移るクライアント。

    無料枠は 1 モデルあたり 1 日 20 リクエストで、1 回の生成には最良でも
    20 リクエストかかる。1 モデルではAI モードを完走できないため、
    開発時に複数モデルの枠を足し合わせて使えるようにする。

    **ラウンドロビンではなくフェイルオーバーである。** 確認したいのは
    「AI が全科目を割り振った時間割」であってモデルの比較ではないので、
    チャンクごとに品質の違うモデルが混ざると何の結果なのか分からなく
    なる。第 1 モデルを使い切るまで使い、あふれた分だけ次へ回す。

    枠切れ以外の失敗ではモデルを切り替えない。それは一時的な失敗であり、
    呼び出し側の再試行で解決しうるためである。
    """

    def __init__(
        self,
        make_client,
        models: list[str],
        on_switch=None,
    ) -> None:
        if not models:
            raise ValueError("モデルが 1 つも指定されていません")
        self._make_client = make_client
        self._models = list(models)
        self._index = 0
        self._clients: dict[str, GeminiClient] = {}
        self._on_switch = on_switch

    @property
    def current_model(self) -> str | None:
        """次に使うモデル。全て枯渇していれば None。"""
        if self._index >= len(self._models):
            return None
        return self._models[self._index]

    def generate(self, prompt: str) -> str:
        while self._index < len(self._models):
            model = self._models[self._index]
            client = self._clients.get(model)
            if client is None:
                client = self._clients[model] = self._make_client(model)
            try:
                return client.generate(prompt)
            except (QuotaExceededError, ModelBusyError) as error:
                self._index += 1
                if self._on_switch is not None:
                    self._on_switch(model, self.current_model, error)
        raise GeminiError(
            f"指定された全 {len(self._models)} モデルが利用枠に達しました"
            f"（{'、'.join(self._models)}）"
        )
