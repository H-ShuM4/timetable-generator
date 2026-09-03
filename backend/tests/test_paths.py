"""保存先のルート。テストが事務局のデータを踏まないための逃がし口。"""
import os
import subprocess
import sys
from pathlib import Path

from app import paths

BACKEND = Path(__file__).resolve().parents[1]


def test_the_default_root_is_the_backend_directory():
    """環境変数が無ければ従来どおり。事務局の運用では何も変わらない。"""
    assert paths.storage_root() == BACKEND


def test_an_environment_variable_moves_the_root(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path))
    assert paths.storage_root() == tmp_path


def test_every_store_follows_the_root(tmp_path):
    """セッション・ログ・設定・API キーが 1 つ残らず移ること。

    E2E はサーバを別プロセスで起動するので conftest の monkeypatch が
    届かない。1 つでも取りこぼすと、実行のたびに `backend/data/sessions`
    （`session_store.MAX_SESSIONS` 件まで）へ書き込み、事務局が保存した
    時間割を追い出す。
    別プロセスで確かめる以外に確かめようがない。
    """
    code = (
        "from app.session_store import SESSIONS_DIR\n"
        "from app.logging.session_logger import DEFAULT_LOG_DIR\n"
        "from app.settings_store import DEFAULT_ENV_PATH, DEFAULT_SETTINGS_PATH\n"
        "for p in (SESSIONS_DIR, DEFAULT_LOG_DIR, DEFAULT_ENV_PATH, DEFAULT_SETTINGS_PATH):\n"
        "    print(p)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, paths.ENV_VAR: str(tmp_path), "PYTHONPATH": str(BACKEND)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    written = result.stdout.split()
    assert len(written) == 4
    for path in written:
        assert path.startswith(str(tmp_path)), f"{path} が root の外にある"
