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


def test_the_rail_shows_which_half_of_the_term_a_class_runs(run_js):
    """前①・後① は学期の前半、前②・後② は後半。開講期間の指定が無ければ
    レールは全高になる。文字で [後①] と書く代わりに形で示す。"""
    assert run_js("timetable_render.js")["card_classes"] == [
        'class="card source-gemini"',
        'class="card source-prelock quarter-first"',
        'class="card source-manual quarter-second"',
    ]


def test_every_card_carries_a_rail(run_js):
    assert run_js("timetable_render.js")["rail_count"] == 3


def test_the_rail_is_described_in_words_for_anyone_who_cannot_see_it(run_js):
    """レールは形だけなので、同じ内容を title に持たせる。"""
    assert run_js("timetable_render.js")["card_titles"] == [
        "AI 配置", "事前ロック・後①", "手動編集・前②",
    ]


def test_the_year_chip_uses_one_step_per_year(run_js):
    """年次は順序のあるデータなので、色相ではなく藍の濃淡 4 段で表す。"""
    assert run_js("timetable_render.js")["year_chips"] == [
        'class="card-year y2"', 'class="card-year y3"', 'class="card-year y4"',
    ]


def test_a_violating_card_is_marked(run_js):
    """違反は朱。事務で訂正を書き入れる色をその意味だけに使う。"""
    assert "violating" in run_js("timetable_render.js")["violating_html"]


def test_the_teacher_view_gathers_classes_across_departments(run_js):
    """82 名中 56 名が 3 学科以上にまたがる。学科のビューを渡り歩かずに
    1 人の週の予定が読めること。"""
    out = run_js("timetable_render.js")
    assert out["teacher_view_codes"] == ["M1", "A1", "J1"]


def test_the_teacher_view_names_the_department_instead_of_the_teacher(run_js):
    """担当が固定されているので、カードには学科を出す。"""
    assert run_js("timetable_render.js")["teacher_view_meta"] == [
        "経営・必修", "会計・必修", "短期大学部・必修",
    ]


def test_the_teacher_view_leaves_out_the_other_term(run_js):
    """後期の科目は前期のグリッドに出さない。"""
    assert "L1" not in run_js("timetable_render.js")["teacher_view_codes"]


def test_the_teacher_panel_shows_the_load_against_the_working_conditions(run_js):
    """「この先生、水曜が詰まりすぎでは」に気づけるようにする。"""
    panel = run_js("timetable_render.js")["teacher_panel"]
    assert "渡り先生" in panel
    assert "区分 <b>専任</b>" in panel
    assert "研究日 <b>金</b>" in panel
    assert "前期 <b>3</b> コマ" in panel
    assert "通年 <b>4</b> コマ" in panel


def test_the_teacher_panel_stays_out_of_the_way_in_the_department_view(run_js):
    out = run_js("timetable_render.js")
    assert out["teacher_panel_hidden"] is False
    assert out["panel_hidden_in_department_view"] is True


def test_the_result_screen_says_why_a_subject_could_not_be_inherited(run_js):
    """「制約に合いません」だけでは事務局が追えない。

    どの制約に、どの科目とぶつかったのかを画面に出す。
    """
    out = run_js("timetable_render.js")
    assert out["skip_block_hidden"] is False
    assert out["skip_count"] == "1"
    assert "[H1]" in out["skip_html"]
    assert "重複しています" in out["skip_html"]
    assert "相手: 踏襲できた科目" in out["skip_html"]


def test_the_skipped_count_is_not_vermilion(run_js):
    """朱は制約違反だけに使う。踏襲できなかったのは違反ではない（§8.2）。"""
    assert run_js("timetable_render.js")["skip_count_is_alert"] is False


def test_the_skipped_block_stays_out_of_the_way_in_other_modes(run_js):
    """モックと AI モードでは空になるので、丸ごと隠す。"""
    assert run_js("timetable_render.js")["skip_block_hidden_when_empty"] is True


def test_a_subject_name_in_the_skipped_list_cannot_inject_markup(run_js):
    html = run_js("timetable_render.js")["skip_html"]
    assert "<img" not in html
    assert "&lt;img" in html
