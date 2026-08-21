"""ブラウザ側のセッション復元。node があるときだけ走る。"""


def test_a_restored_session_opens_the_result_tab(run_js):
    """結果タブは生成完了時にしか有効化されておらず、復元しても結果へ
    辿り着けなかった。"""
    row = run_js("restore_session.js")["with_result"]
    assert row["session_id"] == "abc123"
    assert row["generate_tab_enabled"] is True
    assert row["result_tab_enabled"] is True
    assert "生成結果を復元しました" in row["note"]


def test_a_session_without_a_result_leaves_the_result_tab_closed(run_js):
    row = run_js("restore_session.js")["without_result"]
    assert row["generate_tab_enabled"] is True
    assert row["result_tab_enabled"] is False
    assert "生成結果" not in row["note"]


def test_a_session_the_server_has_forgotten_is_dropped(run_js):
    """保存期間を過ぎたセッション ID を持ち続けない。"""
    row = run_js("restore_session.js")["nothing_saved"]
    assert row["session_id"] is None
    assert row["generate_tab_enabled"] is False
    assert row["remembered"] is None
