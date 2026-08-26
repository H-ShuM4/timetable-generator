"""セッション・ログ・設定を書き込むルート。

既定は backend/ 自身で、事務局の運用では従来と同じ場所を使う。

環境変数で逃がせるようにしてあるのは、E2E テストがサーバを**別プロセス**
で起動するためである。`tests/conftest.py` の `isolated_storage` は
monkeypatch なので別プロセスには届かず、そのままでは保存済みセッション
（上限 20 件）とログを実行のたびに追い出してしまう。
"""
import os
from pathlib import Path

ENV_VAR = "TIMETABLE_DATA_DIR"

BACKEND_DIR = Path(__file__).resolve().parents[1]


def storage_root() -> Path:
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else BACKEND_DIR
