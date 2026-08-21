"""ブラウザ側のセッション復元。node があるときだけ走る。

実機でしか見つからなかった不具合が 2 度続いたため、DOM のスタブ上で
最低限の動作を固定する。ブラウザ全体を用意しなくても「復元後にどの
タブが有効になるか」はここで確かめられる。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "js" / "restore_session.js"


@pytest.fixture(scope="module")
def outcome():
    if shutil.which("node") is None:
        pytest.skip("node が無い環境ではフロントの検証を飛ばす")
    result = subprocess.run(
        ["node", str(SCRIPT)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_restored_session_opens_the_result_tab(outcome):
    """結果タブは生成完了時にしか有効化されておらず、復元しても結果へ
    辿り着けなかった。"""
    row = outcome["with_result"]
    assert row["session_id"] == "abc123"
    assert row["generate_tab_enabled"] is True
    assert row["result_tab_enabled"] is True
    assert "生成結果を復元しました" in row["note"]


def test_a_session_without_a_result_leaves_the_result_tab_closed(outcome):
    row = outcome["without_result"]
    assert row["generate_tab_enabled"] is True
    assert row["result_tab_enabled"] is False
    assert "生成結果" not in row["note"]


def test_a_session_the_server_has_forgotten_is_dropped(outcome):
    """保存期間を過ぎたセッション ID を持ち続けない。"""
    row = outcome["nothing_saved"]
    assert row["session_id"] is None
    assert row["generate_tab_enabled"] is False
    assert row["remembered"] is None
