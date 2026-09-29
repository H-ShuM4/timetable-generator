"""時間割 Excel の「様式」。どんな見た目にするかをここにまとめる。

事務局から受け取った見本「2026時間割（新経営学科）.xlsx」に合わせてある。
**何をどこにどう書くかの決め事だけを置き、書き込む手順は持たない**
（手順は同じフォルダの excel_writer.py）。見た目を直したいときは、まず
ここを見れば足りるようにしてある。

置いてあるもの。

    シートの割り当て      SHEET_PLAN・DEPARTMENT_TITLES・DEPARTMENT_YEARS
    授業時間と網掛け      PERIOD_TIMES・is_shaded
    列の並びと幅          Column・day_columns・intensive_columns
    列の占める範囲        Span
    書体・罫線・塗り      GOTHIC 以下の定数
    科目のまとめ方        Group・group_subjects
"""
from dataclasses import dataclass

from openpyxl.styles import Border, Font, PatternFill, Side

from app.models.enums import Category, Department, Term
from app.models.timeslot import DAYS, PERIODS

SHEET_PLAN: tuple[tuple[str, Department, Term], ...] = (
    ("経営・前期", Department.MANAGEMENT, Term.SPRING),
    ("経営・後期", Department.MANAGEMENT, Term.FALL),
    ("会計・前期", Department.ACCOUNTING, Term.SPRING),
    ("会計・後期", Department.ACCOUNTING, Term.FALL),
    ("短大・前期", Department.JUNIOR, Term.SPRING),
    ("短大・後期", Department.JUNIOR, Term.FALL),
)

DEPARTMENT_TITLES = {
    Department.MANAGEMENT: "経営学科",
    Department.ACCOUNTING: "会計学科",
    Department.JUNIOR: "短期大学部",
}

REMOTE_DAY = "金"
"""遠隔科目が集まる曜日（H8）。

大学は遠隔列が ○ か × で埋まっていて空欄が無いため、金曜へ来るのは遠隔
科目だけになる。短大は ○ か空欄で × が無く、対面も金曜に来うる。
"""

PERIOD_TIMES = {
    1: ("8：50", "10：30"),
    2: ("10：40", "12：20"),
    3: ("13：10", "14：50"),
    4: ("15：00", "16：40"),
    5: ("16：50", "18：30"),
}
"""各時限の授業時間。時限の欄に「1時限／8：50〜10：30」と 2 段で出す。"""

ZOOM = 40
"""開いたときの表示倍率（%）。

A3 横 1 枚ぶんの幅があるので、既定の 100% では右端が画面に入らない。
事務局が毎回縮めなくて済むように、ここで決めておく。
"""

SHADED = "DDDDDD"
"""市松に敷く網掛けの色。見本で使われていたものと同じ。"""


def is_shaded(day: str, period: int) -> bool:
    """その曜日・時限に網掛けを敷くか。

    曜日と時限を足して偶数なら敷く。**市松模様にすることで、どの升目が
    どの曜日・時限かを追いやすくする。** 横に 5 曜日ぶん並ぶので、目が
    1 行ずれると別の曜日を読んでしまう。
    """
    return (DAYS.index(day) + period) % 2 == 0

CATEGORY_MARKS = {Category.REQUIRED: "必", Category.ELECTIVE_REQUIRED: "選必"}
"""短大の「必修」欄に出す記号。選択は空欄のままにする。"""

DEPARTMENT_YEARS = {
    Department.MANAGEMENT: (1, 2, 3, 4),
    Department.ACCOUNTING: (1, 2, 3, 4),
    Department.JUNIOR: (1, 2),
}
"""学科ごとの配当年次。**その学期に 1 件も無くても行は出す。**

前期と後期で表の形が変わると、並べて見たときに読み違える。空でも枠を
残しておけば、事務局が「ここは今年度なし」と分かる。"""


# ---------------------------------------------------------------- 列の定義

@dataclass(frozen=True)
class Column:
    """曜日ブロックの中の 1 列。"""

    key: str
    title: str
    width: float


LOTTERY = Column("lottery", "抽選", 5.6)
CAPACITY = Column("capacity", "", 5.6)
NAME = Column("name", "授業科目名", 37.4)
QUARTER = Column("quarter", "備考", 7.0)
TEACHER = Column("teacher", "教員", 15.6)
ROOM = Column("room", "教室", 10.6)
REQUIRED_ONLY = Column("required_only", "備考", 5.6)
CATEGORY = Column("category", "必修", 6.5)

SPACER_WIDTH = 4.0
YEAR_COLUMN_WIDTH = 5.6
PERIOD_COLUMN_WIDTH = 10.5
"""時限の列の幅。

「10：30」が折り返さずに収まる幅を取る。狭いと授業時間が途中で折れて
読めなくなる。中央に寄せるので、短い「8：50」は自然に字下がりして
上下がそろう。
"""

INTENSIVE_HEADING = "集中"

SPANNING_KEYS = frozenset({"name", "quarter", "required_only", "category"})
"""1 科目につき 1 回だけ書き、教員の人数ぶん縦に結合する項目。

教員だけは 1 行に 1 名ずつ並べる。抽選・人数・教室は空欄のまま残す。
"""


def day_columns(department: Department, day: str) -> tuple[Column, ...]:
    if department is Department.JUNIOR:
        return (LOTTERY, CAPACITY, NAME, QUARTER, TEACHER, ROOM, CATEGORY)
    if day == REMOTE_DAY:
        return (LOTTERY, CAPACITY, NAME, TEACHER, REQUIRED_ONLY)
    return (LOTTERY, CAPACITY, NAME, TEACHER, ROOM, REQUIRED_ONLY)


def intensive_columns(department: Department) -> tuple[Column, ...]:
    tail = CATEGORY if department is Department.JUNIOR else REQUIRED_ONLY
    return (NAME, TEACHER, ROOM, tail)


@dataclass(frozen=True)
class Span:
    """ブロックの中の 1 項目が、どの列からどの列までを占めるか。

    **曜日ブロックと集中ブロックを同じ形で表すためのもの。** 曜日は
    1 項目 1 列で済むが、集中を表の下へ回すときは既にある列幅を流用する
    ため、科目名や教員を横に結合して広げる必要がある。両方を「列の範囲」
    として持てば、書き込む側は 1 通りで済む。

    以前はこの 2 つを別々の処理で書いており、片方を直してもう片方を
    直し忘れる取りこぼしが実際に起きた（日付の置き場所がずれた）。
    """

    first: int
    last: int
    key: str
    title: str = ""

    @property
    def merged(self) -> bool:
        return self.last > self.first


# ---------------------------------------------------------------- 体裁

GOTHIC = "ＭＳ ゴシック"
P_GOTHIC = "ＭＳ Ｐゴシック"

TITLE_FONT = Font(name=GOTHIC, size=18)
DATE_FONT = Font(name=GOTHIC, size=18, bold=True)
DAY_FONT = Font(name=P_GOTHIC, size=18)
HEADER_FONT = Font(name=GOTHIC, size=12)
BODY_FONT = Font(name=GOTHIC, size=14)
SMALL_FONT = Font(name=GOTHIC, size=12)
ROOM_FONT = Font(name=GOTHIC, size=18)

HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")

MEDIUM = Side(style="medium")
DOTTED = Side(style="dotted")

# 横の区切りは 3 段階にする。**同じ年次の中には線を引かない。**
#   時限のあいだ … 太い実線。紙を追うときの大きな段
#   年次のあいだ … 点線。同じ時限の中の小さな段
#   年次の中     … 線なし。1 科目が教員の人数ぶん行を使うので、
#                   1 行ごとに線を引くと科目の切れ目が分からなくなる
BETWEEN_PERIODS = MEDIUM
BETWEEN_YEARS = DOTTED
WITHIN_YEAR = None

TITLE_ROW, DAY_ROW, HEADER_ROW, FIRST_BODY_ROW = 1, 2, 3, 4

TITLE_HEIGHT = 48.75
DAY_HEIGHT = 27.75
BODY_HEIGHT = 23.5

ROWS_FOR_PERIOD_LABEL = 5
"""時限の欄に要る最低の行数。

「1時限／8：50／〜／10：30」で 5 行ぶんの高さを使う。科目が少ない時限で
ブロックがこれより短いと、授業時間が行の下に隠れて読めない。足りない
ぶんは最後の年次に足して背を伸ばす。
"""


def frame(*, left=DOTTED, right=DOTTED, top=None, bottom=None) -> Border:
    return Border(left=left, right=right, top=top, bottom=bottom)


def row_rule(*, last_row: bool, last_year: bool):
    """その行の下に引く線を選ぶ。"""
    if not last_row:
        return WITHIN_YEAR
    return BETWEEN_PERIODS if last_year else BETWEEN_YEARS


# ---------------------------------------------------------------- 並べ替え

CATEGORY_ORDER = {
    Category.REQUIRED: 0,
    Category.ELECTIVE_REQUIRED: 1,
    Category.ELECTIVE: 2,
}


@dataclass
class Group:
    """1 つのコマに入る、同じ科目名の一かたまり。

    課題研究Ⅰは 18 名、卒業研究Ⅰは 16 名が担当する。見本と同じく科目名は
    1 回だけ書き、教員を続く行に並べる（科目名と備考のセルは縦に結合する）。
    """

    name: str
    quarter: str
    category: Category
    teachers: list[str]
    """Excel 上の元の表記（「築　雅之」のように全角空白で姓名を分けた形）。

    突合に使う正規化済みの氏名ではない。事務局が長年その形で紙を作って
    きたので、書き出すときは元に戻す。"""

    @property
    def height(self) -> int:
        return len(self.teachers)


def group_subjects(subjects: list) -> list[Group]:
    ordered = sorted(
        subjects, key=lambda s: (CATEGORY_ORDER.get(s.category, 9), s.name, s.code)
    )
    groups: list[Group] = []
    for subject in ordered:
        quarter = subject.quarter.value if subject.quarter else ""
        shown = subject.teacher_display or subject.teacher
        if groups and groups[-1].name == subject.name and groups[-1].quarter == quarter:
            groups[-1].teachers.append(shown)
            continue
        groups.append(Group(subject.name, quarter, subject.category, [shown]))
    return groups
