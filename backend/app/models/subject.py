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
    is_joint: bool = False
    """Excel の `合同(経・会)` 列が ○ か。ペアリング前の生のフラグ。"""

    joint_id: str | None = None
    """ペアリング成立後に付与される合同グループ ID。"""

    slots_required: int = 1
    requires_consecutive: bool = False
    fixed_slot: tuple[TimeSlot, ...] | None = None
    is_intensive: bool = False
    is_seminar: bool = False
