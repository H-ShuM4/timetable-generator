"""Gemini API クライアント。

失敗はすべて GeminiError に包む。呼び出し側は再試行するだけでよく、
SDK の例外型に依存しない。
"""
from typing import Protocol

from app.gemini.prompts import RESPONSE_SCHEMA


class GeminiError(Exception):
    """Gemini 呼び出しに関するあらゆる失敗。"""


class GeminiClient(Protocol):
    def generate(self, prompt: str) -> str:
        """プロンプトを送り、応答テキストを返す。"""


class RealGeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
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
            raise GeminiError(str(error)) from error

        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("空の応答が返りました")
        return text
