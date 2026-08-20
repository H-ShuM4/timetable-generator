"""前期・後期にまたがる科目の対応付け。

日本語リテラシーⅠとⅡのように、同じ担当教員が前期と後期に続けて
受け持つ科目を 1 組にまとめる。事務局の運用では、この 2 つは同じ
曜日・時限に置くことになっている（H12）。

ゼミ科目（課題研究・卒業研究）はさらに、3 年生と 4 年生が交流できる
よう可能な限り隣り合う時限に置きたい。これは制約ではなく好みなので
`adjacent_id` として別に持つ。

**対応付けは教員で取る。** 授業コードの末尾は一致しないことがある
（荒牧裕一の課題研究は Ⅰ が B63120、Ⅱ が B63200）。同じ教員が同じ
科目を 2 コマ持つ場合（鈴木昭彦の日本語リテラシーⅢが A50401 と
A50406）は、コード順に 1 対 1 で対応させる。
"""
import json
from collections import defaultdict
from pathlib import Path

from app.models.subject import Subject

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "paired_subjects.json"


def load_pair_config(path: Path | None = None) -> dict[str, list[list[str]]]:
    """設定ファイルを読む。無い・壊れている場合は対応付けを行わない。

    この機能が使えなくても時間割は作れる。設定ファイルの不備で生成
    全体を止めるほうが害が大きい。
    """
    target = Path(path) if path else _CONFIG_PATH
    if not target.exists():
        return {"same_slot_across_terms": [], "adjacent_periods": []}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return {
            "same_slot_across_terms": raw.get("same_slot_across_terms", []) or [],
            "adjacent_periods": raw.get("adjacent_periods", []) or [],
        }
    except (json.JSONDecodeError, ValueError, TypeError, OSError):
        return {"same_slot_across_terms": [], "adjacent_periods": []}


def _link_family(
    subjects: list[Subject], family: list[str], prefix: str, index: int, attribute: str
) -> int:
    """1 つの組み合わせについて対応付け、次に使う連番を返す。

    family は ["課題研究Ⅰ", "課題研究Ⅱ"] のような base_name の並び。
    学科と教員が同じものを、family の順に 1 対 1 で結ぶ。
    """
    by_slot_in_family: dict[tuple, dict[str, list[Subject]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for subject in subjects:
        if subject.base_name in family:
            key = (subject.department.value, subject.teacher)
            by_slot_in_family[key][subject.base_name].append(subject)

    for key in sorted(by_slot_in_family):
        members = by_slot_in_family[key]
        if len(members) < len(family):
            # 片方の学期しか持っていない教員。対応付けは成立しない。
            continue
        columns = [sorted(members[name], key=lambda s: s.code) for name in family]
        for row in zip(*columns):
            group_id = f"{prefix}{index:03d}"
            index += 1
            for subject in row:
                setattr(subject, attribute, group_id)
    return index


def assign_pair_ids(subjects: list[Subject], config_path: Path | None = None) -> None:
    """pair_id と adjacent_id を付与する。subjects を破壊的に書き換える。"""
    config = load_pair_config(config_path)

    index = 1
    for family in config["same_slot_across_terms"]:
        index = _link_family(subjects, list(family), "P", index, "pair_id")

    index = 1
    for family in config["adjacent_periods"]:
        index = _link_family(subjects, list(family), "N", index, "adjacent_id")
