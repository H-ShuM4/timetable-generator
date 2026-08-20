"""科目 1 件を表すデータクラス。仕様書 §5.1 に対応する。"""
from dataclasses import dataclass, field

from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot


@dataclass(slots=True)
class Subject:
    code: str
    """授業コード。▲科目は 2 行が 1 件に集約されるため一意になる。"""

    name: str
    """Excel 上の科目名称（原文）。"""

    base_name: str
    """先頭の ▲、接尾辞の :会、【再】を除いた正規化名。

    ゼミ判定と合同ペアリングはこの値で行う。
    """

    department: Department
    year: int
    term: Term
    quarter: Quarter | None
    category: Category
    courses: list[str] = field(default_factory=list)
    teacher: str = ""
    is_remote: bool = False
    """Excel の `遠隔` 列が ○ か。遠隔で行うため金曜に置く（H8）。"""

    is_remote_prohibited: bool = False
    """Excel の `遠隔` 列が × か。遠隔で行えないため金曜に置けない（H8）。

    ○ の否定ではない。空欄は「どちらでもよい」であり、この値も
    `is_remote` も False になる。大学シートは全行が ○ か × で
    埋まっているが、短大シートは ○ と空欄しか無く × が存在しない。
    """
    is_joint: bool = False
    """Excel の `合同(経・会)` 列が ○ か。ペアリング前の生のフラグ。"""

    joint_id: str | None = None
    """ペアリング成立後に付与される合同グループ ID。"""

    pair_id: str | None = None
    """前期・後期をまたぐ対応付けの ID（H12）。

    日本語リテラシーⅠとⅡのように、同じ教員が続けて受け持つ 2 科目に
    同じ値が入る。H12 はこれらを同じ曜日・時限に置くことを要求する。
    """

    adjacent_id: str | None = None
    """隣り合う時限に置きたい科目群の ID。

    課題研究（3 年）と卒業研究（4 年）を同じゼミ内で隣接させ、学年を
    またいだ交流ができるようにする。**制約ではなく好みである。**
    隣接できなければ離れたコマに置く。
    """

    slots_required: int = 1
    requires_consecutive: bool = False
    fixed_slot: tuple[TimeSlot, ...] | None = None
    is_intensive: bool = False
    is_seminar: bool = False
    """ゼミ科目群（`config/seminar_subjects.json`）に属するか。

    **制約判定では使われていない。** H2 の除外条件が「双方がゼミ科目で
    base_name が同一」から「base_name が同一」へ一般化された際に不要に
    なった。事務局の運用では担当教員違いの同一科目はゼミかどうかに
    関係なく同一コマへ集約するため、ゼミという区分をスケジューリングで
    区別する必要がない。

    どの科目がゼミなのかという定義自体は本学のカリキュラム記述として
    意味があるため保持している。将来これを参照する機能が現れなければ、
    このフィールドと設定ファイルは削除してよい。
    """
