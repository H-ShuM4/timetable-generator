"""生成画面の踏襲モードまわり。node があるときだけ走る。

踏襲モードそのものは前年度の実データが無いと E2E で通せない
（設計仕様 §13）。画面側の挙動はここで押さえる。
"""


def test_inherit_is_available_when_both_previous_files_arrived(run_js):
    row = run_js("retarget_panel.js")["both_present"]
    assert row["inherit_disabled"] is False
    assert row["note_hidden"] is True


def test_inherit_is_blocked_when_the_previous_teacher_list_is_missing(run_js):
    """時間割だけでは 1 件も引き継がれない。

    研究日の比較が「前年度＝なし」対「今年度＝あり」となって全専任が
    組み替え対象へ落ちる。実データでは 613 件中 613 件が組み替えになる。
    """
    row = run_js("retarget_panel.js")["timetable_only"]
    assert row["inherit_disabled"] is True
    assert "前年度の教員一覧" in row["note"]
    assert "前年度の時間割" not in row["note"], "足りているものを求めない"


def test_inherit_is_blocked_when_the_previous_timetable_is_missing(run_js):
    row = run_js("retarget_panel.js")["teachers_only"]
    assert row["inherit_disabled"] is True
    assert "前年度の時間割" in row["note"]
    assert "前年度の教員一覧" not in row["note"]


def test_both_missing_files_are_named(run_js):
    row = run_js("retarget_panel.js")["neither"]
    assert row["inherit_disabled"] is True
    assert "前年度の時間割" in row["note"]
    assert "前年度の教員一覧" in row["note"]


def test_nothing_loaded_yet_also_blocks_inherit(run_js):
    """読み込み前に生成タブを開いても、押せないことが分かること。"""
    assert run_js("retarget_panel.js")["no_summary_yet"]["inherit_disabled"] is True


def test_selecting_inherit_then_losing_the_files_falls_back_to_mock(run_js):
    """押せないモードが選ばれたままにしない。

    （DOM スタブはラジオの排他を模していないので、モック側が選ばれたこと
    だけを見る。実機ではブラウザが踏襲側を外す。）
    """
    row = run_js("retarget_panel.js")["falls_back_to_mock"]
    assert row["inherit_disabled"] is True
    assert row["mock_checked"] is True


def test_the_retarget_list_leads_with_how_many_change_and_how_many_stay(run_js):
    """189 件のチェックボックスをベタ並びにされても、規模が読み取れない。"""
    text = run_js("retarget_panel.js")["list"]["summary_text"]
    assert "613 科目のうち 6 件を組み替え" in text
    assert "607 件は前年度のコマのまま" in text


def test_the_retarget_list_groups_by_reason_with_the_biggest_first(run_js):
    row = run_js("retarget_panel.js")["list"]
    assert row["group_headings"] == [
        "非専任（非常勤） 3",
        "非専任（特任） 2",
        "前年度に存在しない新規科目 1",
    ]
    assert row["group_count"] == 3


def test_the_groups_start_folded(run_js):
    """実データでは非常勤だけで 141 件ある。開いたまま並べると規模が読めない。"""
    assert run_js("retarget_panel.js")["list"]["groups_start_closed"] is True


def test_every_subject_is_listed_once(run_js):
    assert run_js("retarget_panel.js")["list"]["codes"] == [
        "P0", "P1", "P2", "S0", "S1", "N0"
    ]


def test_clear_all_unchecks_every_subject(run_js):
    """一部だけ触りたいとき、189 件を 1 つずつ外させない。"""
    assert run_js("retarget_panel.js")["list"]["all_cleared"] is True


def test_a_subject_name_from_excel_cannot_inject_markup(run_js):
    row = run_js("retarget_panel.js")["list"]
    assert row["has_raw_tag"] is False
    assert row["has_escaped_tag"] is True


def test_nothing_to_retarget_says_so_without_blaming_the_files(run_js):
    """前年度がそろっていて 0 件なら、それは正常な結果である。

    以前は「前年度ファイルを読み込んでください」と出しており、
    そろっているのに読み込めていないように見えた。
    """
    text = run_js("retarget_panel.js")["empty"]
    assert "組み替えが要る科目はありません" in text
    assert "読み込んでください" not in text
