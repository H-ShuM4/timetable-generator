"""API キーと生成設定の読み書き。API キーの全文は返さない。"""
from fastapi import APIRouter

from app.api.schemas import ApiKeyIn, SettingsIn, SettingsOut
from app.settings_store import AppSettings, SettingsStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

store = SettingsStore()


def _current() -> SettingsOut:
    settings = store.load()
    masked = store.masked_api_key()
    return SettingsOut(
        model=settings.model,
        max_retries=settings.max_retries,
        api_key_masked=masked,
        has_api_key=masked is not None,
    )


@router.get("", response_model=SettingsOut)
async def get_settings() -> SettingsOut:
    return _current()


@router.put("", response_model=SettingsOut)
async def put_settings(payload: SettingsIn) -> SettingsOut:
    store.save(AppSettings(model=payload.model, max_retries=payload.max_retries))
    return _current()


@router.put("/api-key", response_model=SettingsOut)
async def put_api_key(payload: ApiKeyIn) -> SettingsOut:
    store.set_api_key(payload.api_key)
    return _current()


@router.delete("/api-key", response_model=SettingsOut)
async def delete_api_key() -> SettingsOut:
    store.delete_api_key()
    return _current()
