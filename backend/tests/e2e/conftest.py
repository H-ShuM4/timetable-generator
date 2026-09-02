"""実ブラウザから本物のサーバを叩くための土台。

ユニットテストは `TestClient` でアプリを直接呼ぶが、それでは
fetch・SSE・ドラッグ&ドロップ・ダウンロードが検証できない。ここだけは
uvicorn を別プロセスで起こし、Chromium から触る。
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
BACKEND = E2E_DIR.parents[1]
ROOT = E2E_DIR.parents[2]

STARTUP_TIMEOUT_SECONDS = 30.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until_listening(process: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"サーバが起動前に終了しました (exit={process.returncode})\n"
                f"{process.stderr.read() if process.stderr else ''}"
            )
        with socket.socket() as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise RuntimeError(f"サーバが {STARTUP_TIMEOUT_SECONDS} 秒以内に起動しませんでした")


@pytest.fixture(scope="session")
def live_server(tmp_path_factory) -> str:
    """テスト専用の保存先を持つ uvicorn を起こし、URL を返す。

    `TIMETABLE_DATA_DIR` を渡すのが要点。これを忘れると
    `backend/data/sessions`（上限 20 件）と `backend/logs` へ書き込み、
    事務局が保存した時間割を実行のたびに追い出す。親の conftest の
    `isolated_storage` は monkeypatch なので別プロセスには届かない。
    """
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND,
        env={
            **os.environ,
            "TIMETABLE_DATA_DIR": str(tmp_path_factory.mktemp("server-root")),
            "PYTHONPATH": str(BACKEND),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_until_listening(process, port)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def sample_xlsx() -> list[Path]:
    """事務局が実際に投入している 2 本。ユニットテストと同じ実データ。"""
    from tests.conftest import CURRICULUM_XLSX, TEACHERS_XLSX

    if CURRICULUM_XLSX is None or TEACHERS_XLSX is None:
        pytest.skip("実データが無い環境では E2E を飛ばす")
    return [CURRICULUM_XLSX, TEACHERS_XLSX]
