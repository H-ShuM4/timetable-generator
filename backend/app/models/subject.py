"""科目 1 件を表すデータクラス。仕様書 §5.1 に対応する。

**科目名は 3 つの粒度で持つ。** どれを使うかで結果が変わるので、
最初にここを押さえてほしい。過去に取り違えて不具合になっている。

    name        Excel の原文そのまま
    base_name   先頭の ▲、接尾辞の :会、【再】を外したもの
    class_group base_name からさらにクラス記号【A】（A）を外したもの

    name                    base_name          class_group
    ─────────────────────────────────────────────────────────────
    ▲英語Ⅰ【A】:会         英語Ⅰ【A】        英語Ⅰ
    情報リテラシーⅠ【A】   情報リテラシーⅠ【A】  情報リテラシーⅠ
    経営情報活用（A）       経営情報活用（A）  経営情報活用
    日本語リテラシーⅠ・Ⅱ【再】  日本語リテラシーⅠ・Ⅱ  日本語リテラシーⅠ・Ⅱ

使い分けはこうなっている。

    base_name    設定ファイル（department_rules.json・paired_subjects.json）
                 との突き合わせ、ゼミ判定、合同ペアリング。
                 **クラス記号を残す。** 経営の英語Ⅰ【A】と会計の
                 英語Ⅰ【A】を組にしたいので、ここで潰してはいけない
    class_group  学生側の衝突判定（H2・H3）。英語Ⅰ【A】と【B】は
                 1 科目を教員ごとに割ったもので、学生が受けるのは
                 どちらか一方なので、同じコマに置いてよい
    name         画面と Excel への表示。判定には使わない
"""
import re
from dataclasses import dataclass, field

from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot

DOUBLE_SLOT_MARKER = "▲"
ACCOUNTING_SUFFIX = ":会"
RETAKE_MARKER = "【再】"

CLASS_MARKER = re.compile(r"[【（][A-Za-zＡ-Ｚａ-ｚ][】）]")
"""クラス分けの記号。英語Ⅰ【A】〜【E】や 経営情報活用（A）のように、
1 科目を教員ごと・開講期ごとに割った印。角括弧と丸括弧の両方が使われている。

**英字 1 文字だけを対象にする。** 【留学生】や（日本国憲法を含む）、
（Photoshop）のような括弧は科目名の一部であって、クラス分けではない。
"""


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

    @property
    def is_retake(self) -> bool:
        """再履修クラスか。

        1 年次に落単した学生が履修するため、配当年次は 1 年でも実際に
        受けるのは 2 年生以降になる。**同じ年次の集団には属さない**ので、
        年次に由来する制約（H2・H3 の学生衝突、H13 の朝学習）から外れる。
        ただし【再】同士は互いに衝突する（2 科目を同時に再履修する学生がいる）。
        """
        return RETAKE_MARKER in self.name

    @property
    def class_group(self) -> str:
        """同じ科目の複数クラスをまとめる名前。

        英語Ⅰ【A】と英語Ⅰ【B】はここで一致する。学生が履修するのは
        そのうち一つなので、同一コマに集約してよい（H2・H3 の除外）。

        **`base_name` とは粒度が違う。** 合同ペアリングは経営の
        英語Ⅰ【A】と会計の英語Ⅰ【A】を組にしたいのでクラス記号が要る。
        クラス記号を外すのは学生側の衝突判定だけにする。
        """
        return CLASS_MARKER.sub("", self.base_name).strip()
