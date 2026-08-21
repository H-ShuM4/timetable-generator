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


def test_the_load_summary_leads_with_the_four_headline_counts(run_js):
    """箇条書きの羅列ではなく、数字を拾える形にする。"""
    assert run_js("restore_session.js")["summary"]["stats"] == ["658", "99", "45", "47"]


def test_each_breakdown_entry_stands_on_its_own(run_js):
    """「会計 234 / 経営 262」と 1 行に潰さず、区切って読めるようにする。"""
    tallies = run_js("restore_session.js")["summary"]["tallies"]
    assert tallies == ["会計", "経営", "必修", "非常勤", "なし"]


def test_warnings_are_amber_not_vermilion(run_js):
    """朱は制約違反だけに使う。警告は違反ではない。"""
    assert run_js("restore_session.js")["summary"]["warning_count_class"] == "count warn"


def test_the_restore_note_does_not_show_the_session_id(run_js):
    """セッション ID は利用者が使う場面が無い。復元された事実だけ伝える。"""
    for key in ("with_result", "without_result"):
        note = run_js("restore_session.js")[key]["note"]
        assert "セッション" not in note
        assert "復元しました" in note


def test_a_warning_shows_its_message_without_the_internal_kind(run_js):
    """[missing_availability] のような識別子は内部用。ログには残る。"""
    text = run_js("restore_session.js")["summary"]["warning_text"]
    assert text == "出勤可能日が空欄です"
    assert "[" not in text
