"""設定画面の予備モデル欄と、ログパネルの開閉。"""


def test_the_fallback_models_are_offered_newest_first(run_js):
    """並び順がそのまま枠切れ時の切り替え順になる。"""
    assert run_js("settings_models.js")["settings"]["candidates"] == [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
    ]


def test_saved_models_come_back_checked(run_js):
    settings = run_js("settings_models.js")["settings"]
    assert settings["checked_after_apply"] == ["gemini-3.6-flash"]


def test_a_model_outside_the_list_is_not_lost(run_js):
    """候補一覧に無い名前は「その他」欄へ戻す。消してはいけない。"""
    assert run_js("settings_models.js")["settings"]["extra_after_apply"] == "自作モデル"


def test_collecting_keeps_the_listed_order_then_free_text(run_js):
    """チェックした順ではなく一覧の並び順で送る。空白と空欄は落とす。"""
    assert run_js("settings_models.js")["settings"]["collected"] == [
        "gemini-3.7-flash", "gemini-3-flash-preview", "手入力A", "手入力B",
    ]


def test_choosing_nothing_sends_nothing(run_js):
    """実務では 1 モデルだけを使う。既定は従来どおりの動作。"""
    assert run_js("settings_models.js")["settings"]["collected_empty"] == []


def test_the_log_toggle_label_follows_the_panel(run_js):
    """開いていれば ▼、畳んでいれば ▲。表示と状態がずれないこと。"""
    assert run_js("settings_models.js")["log_panel"] == [
        {"collapsed": False, "label": "▼"},
        {"collapsed": True, "label": "▲"},
    ]


def test_escaping_covers_quotes_as_well_as_tags(run_js):
    """textContent 経由では引用符が残る。値は属性の中にも入る。"""
    assert run_js("settings_models.js")["escape"]["tag"] == "&lt;b&gt;&amp;&quot;&#39;"
