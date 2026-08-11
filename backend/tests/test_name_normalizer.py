from app.ingest.name_normalizer import normalize_name


def test_removes_ideographic_space():
    assert normalize_name("築　雅之") == "築雅之"


def test_removes_ascii_space():
    assert normalize_name("大嶋 伊佐雄") == "大嶋伊佐雄"


def test_same_person_written_two_ways_matches():
    assert normalize_name("髙橋 暁美") == normalize_name("髙橋　暁美")


def test_variant_kanji_is_unified():
    # 教員一覧は「降籏」、カリキュラムは「降旗」と表記が割れている
    assert normalize_name("降籏　光太郎") == normalize_name("降旗　光太郎")


def test_strips_surrounding_whitespace_and_tabs():
    assert normalize_name("  中村\t雅典 \n") == "中村雅典"


def test_empty_input_returns_empty_string():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""
