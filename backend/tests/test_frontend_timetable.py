"""結果画面の描画とコマ計算。事務局が直接触る部分。"""


def test_a_cell_lists_first_year_through_fourth(run_js):
    """1年→2年→3年→4年の順。同じ年次は科目名、さらに授業コード順。

    科目を別のコマへ移し替えても崩れないよう、描画のたびに並べ直す。
    """
    assert run_js("timetable_render.js")["year_order"] == ["C0", "C1", "C2", "C3", "C4"]


def test_both_sides_of_a_violation_are_marked(run_js):
    assert run_js("timetable_render.js")["violating_codes"] == ["V1", "V2"]


def test_a_two_period_class_keeps_its_shape_when_moved(run_js):
    """掴んだコマを基準に、残りのコマも同じだけずれる。"""
    assert run_js("timetable_render.js")["shifted"] == ["木3", "木4"]


def test_a_move_that_would_leave_the_grid_is_rejected(run_js):
    """枠外になるコマは null。呼び出し側が移動を取りやめる。"""
    assert run_js("timetable_render.js")["shifted_out_of_range"] == ["木5", None]


def test_an_unplaced_class_lands_on_the_slot_it_was_dropped_on(run_js):
    out = run_js("timetable_render.js")
    assert out["from_scratch_single"] == ["月2"]


def test_an_unplaced_two_period_class_takes_the_next_period_too(run_js):
    """▲科目は同一日の連続 2 コマ（H10）。落とした位置を先頭にする。"""
    assert run_js("timetable_render.js")["from_scratch_double"] == ["月2", "月3"]


def test_an_unplaced_two_period_class_cannot_start_at_the_last_period(run_js):
    assert run_js("timetable_render.js")["from_scratch_overflow"] is None


def test_unplaced_classes_are_draggable(run_js):
    """置く手段が画面に無いと、自動配置できなかった科目に手出しできない。"""
    html = run_js("timetable_render.js")["unplaced_html"]
    assert 'draggable="true"' in html
    assert 'data-code="U1"' in html and 'data-code="U2"' in html


def test_subject_names_cannot_break_out_of_the_markup(run_js):
    """科目名は Excel 由来。属性値の中にも入るので引用符まで潰す。"""
    out = run_js("timetable_render.js")
    assert out["escaped_has_raw_tag"] is False
    assert out["escaped_has_raw_quote"] is False
    assert "&lt;script&gt;&quot;x&quot;" in out["escaped_sample"]
