"""保存するファイル名の整え方を見る。

事務局が打った文字がそのままディスクへ、そして Content-Disposition
ヘッダへ乗る。**入力を拒まず、必ず保存できる名前を返す**のが方針。
出力の直前に名前で弾かれると、生成し直しになりかねない。
"""
import pytest

from app.api.export import DEFAULT_NAME, MAX_NAME_LENGTH, safe_filename


def test_an_ordinary_name_is_left_alone():
    assert safe_filename("2026時間割") == "2026時間割"
    assert safe_filename("2026時間割（新経営学科）") == "2026時間割（新経営学科）"


@pytest.mark.parametrize("raw", ["", "   ", None, "...", "///"])
def test_nothing_usable_falls_back_to_the_default(raw):
    """空欄のまま押しても出力できる。"""
    assert safe_filename(raw) == DEFAULT_NAME


@pytest.mark.parametrize("bad", list('\\/:*?"<>|'))
def test_characters_windows_refuses_are_dropped(bad):
    """Windows がファイル名に使えない文字。残すと保存に失敗する。"""
    assert safe_filename(f"時間{bad}割") == "時間割"


@pytest.mark.parametrize("raw", ["時間割\r\n", "時\n間割", "時間割\x00", "時間割\x1b[2J"])
def test_control_characters_are_dropped(raw):
    """改行が混じると Content-Disposition が壊れる。

    Starlette は非 ASCII を百分率符号化するのでヘッダ注入にはならないが、
    そもそも名前に入れる理由が無い。
    """
    cleaned = safe_filename(raw)
    assert "\r" not in cleaned and "\n" not in cleaned
    assert cleaned.startswith("時間割")


def test_a_path_cannot_climb_out_of_the_folder():
    """区切り文字を落とすので、上の階層を指す名前にはならない。"""
    assert safe_filename("../../etc/passwd") == "....etcpasswd"
    assert safe_filename("..\\..\\windows\\system32") == "....windowssystem32"
    assert "/" not in safe_filename("a/b/c")


@pytest.mark.parametrize("raw,expected", [
    ("  時間割  ", "時間割"),
    ("時間割.", "時間割"),
    ("時間割...", "時間割"),
])
def test_spaces_and_trailing_dots_are_trimmed(raw, expected):
    """Windows が黙って落とすので、こちらで落としておく。

    残すと「入力した名前と保存された名前が違う」ことになる。
    """
    assert safe_filename(raw) == expected


@pytest.mark.parametrize("name", ["CON", "nul", "Com1", "LPT9", "aux"])
def test_names_windows_reserves_fall_back(name):
    """この名前のファイルは Windows では作れない。"""
    assert safe_filename(name) == DEFAULT_NAME


def test_a_very_long_name_is_cut():
    """拡張子と保存先のパスを足しても 260 文字に収まる長さへ。"""
    cleaned = safe_filename("あ" * 500)
    assert len(cleaned) == MAX_NAME_LENGTH


def test_the_extension_is_not_added_here():
    """付けるのは呼ぶ側。二重に付かないようにする。"""
    assert safe_filename("時間割.xlsx") == "時間割.xlsx"
