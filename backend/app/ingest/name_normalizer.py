"""教員氏名の表記ゆれを吸収する。

2 つの Excel は空白（全角・半角）と異体字（籏/旗、髙/高 など）で
表記が割れている。突合はすべて正規化後の値で行う。
"""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

_DEFAULT_VARIANTS_PATH = Path(__file__).resolve().parents[2] / "config" / "name_variants.json"

_WHITESPACE = "　 \t\r\n"


@lru_cache(maxsize=1)
def load_variants(path: Path | None = None) -> dict[str, str]:
    """異体字マッピングを読み込む。ファイルが無ければ空辞書を返す。"""
    target = path or _DEFAULT_VARIANTS_PATH
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def normalize_name(raw: str | None) -> str:
    """氏名を突合可能な形に正規化する。

    1. None・空文字はそのまま空文字
    2. 全角・半角の空白およびタブ・改行をすべて除去
    3. NFKC 正規化で全角英数などを揃える
    4. 異体字を代表字に置換
    """
    if not raw:
        return ""
    text = str(raw)
    for char in _WHITESPACE:
        text = text.replace(char, "")
    text = unicodedata.normalize("NFKC", text)
    for variant, canonical in load_variants().items():
        text = text.replace(variant, canonical)
    return text
