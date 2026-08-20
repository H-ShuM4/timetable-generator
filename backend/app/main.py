"""FastAPI エントリポイント。フロントエンドの静的ファイルも配信する。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import export, generate, result, settings, upload

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class NoCacheStaticFiles(StaticFiles):
    """毎回サーバへ問い合わせてから使わせる静的ファイル配信。

    Cache-Control を付けないと、ブラウザは Last-Modified から
    「たぶんまだ新しい」と推測して再検証せずにキャッシュを使う
    （ヒューリスティックキャッシュ）。ページ遷移では HTML が再検証
    されるのに、そこから読む JS・CSS だけ古いまま残るという事故が
    実際に起きた。新機能を足したのに画面に出ない、という形で現れる。

    `no-cache` は「保存してよいが使う前に必ず確認せよ」の意味である。
    変更が無ければ ETag により 304 が返るだけなので転送量は増えない。

    事務局の PC へ更新版を配るたびに手動でキャッシュを消してもらう
    わけにいかないため、サーバ側で解決する。
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

app = FastAPI(title="時間割自動生成システム")
app.include_router(upload.router)
app.include_router(settings.router)
app.include_router(generate.router)
app.include_router(result.router)
app.include_router(export.router)

if FRONTEND_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
