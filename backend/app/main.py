"""FastAPI エントリポイント。フロントエンドの静的ファイルも配信する。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import settings, upload

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="時間割自動生成システム")
app.include_router(upload.router)
app.include_router(settings.router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
