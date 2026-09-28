"""生成結果を、事務局が使ってきた様式の Excel として書き出す。

学科 × 学期で 6 シート。事務局から受け取った「2026時間割（新経営学科）.xlsx」
の体裁に合わせてある。**画面のマトリクス表とは別物である。** 画面は 5 日 ×
5 限の升目に科目を積むが、こちらは曜日を横に並べ、時限と年次で縦に区切る。

    行1  経営学科　前期                                    2026-09-28
    行2  月曜日：対面 │ 火曜日：対面 │ … │ 金曜日：遠隔 │ 集中
    行3  抽選│人数│授業科目名│教員│教室│備考
    行4〜 A列=時限（縦結合） B列=年次（縦結合） その下に科目を縦に並べる

**教員名は Excel の元の表記で書く。** 突合には空白を落とした正規化済みの
氏名を使うが、紙に出すのは「築　雅之」のように全角空白で姓名を分けた形に
する。カリキュラム一覧の 97% がその形で、事務局が長年そう作ってきた。

**教室・抽選・人数は空欄で出す。** カリキュラム一覧にその列が無く、埋める
元が無い。見本のシート名が「教室入」であることからも、ここは事務局が
あとから手で入れる欄である。枠だけ用意して渡す。

**大学と短大で列が違う。**

    大学（経営・会計）  抽選│人数│授業科目名│教員│教室│備考
    短期大学部          抽選│人数│授業科目名│備考│教員│教室│必修

短大にはクオーター科目（前①・前②）が 47 件あり、大学には 1 件も無い。
開講期を書く欄が要るのは短大だけなので、そこだけ科目名の右に「備考」を足し、
末尾の欄を「必修」に変えて必・選必を書き分ける。大学は見本どおり、末尾の
「備考」に必修の「必」だけを出す。

**金曜の教室欄は大学にだけ無い。** 大学のカリキュラム一覧は遠隔列が ○ か ×
で埋まっており（空欄が無い）、H8 により金曜へ来るのは遠隔科目だけになる。
教室が要らないので見本も落としている。短大は ○ か空欄で × が無く、対面科目が
金曜に来 うるため、こちらは残す。
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.constraints.context import Context
from app.models.enums import Category, Department, Term
from app.models.timeslot import DAYS, PERIODS, TimeSlot

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
    2: ("10：40", "12：30"),
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
PERIOD_COLUMN_WIDTH = 7.6

INTENSIVE_HEADING = "集中"


def day_columns(department: Department, day: str) -> tuple[Column, ...]:
    if department is Department.JUNIOR:
        return (LOTTERY, CAPACITY, NAME, QUARTER, TEACHER, ROOM, CATEGORY)
    if day == REMOTE_DAY:
        return (LOTTERY, CAPACITY, NAME, TEACHER, REQUIRED_ONLY)
    return (LOTTERY, CAPACITY, NAME, TEACHER, ROOM, REQUIRED_ONLY)


def intensive_columns(department: Department) -> tuple[Column, ...]:
    tail = CATEGORY if department is Department.JUNIOR else REQUIRED_ONLY
    return (NAME, TEACHER, ROOM, tail)


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


def _frame(*, left=DOTTED, right=DOTTED, top=None, bottom=None) -> Border:
    return Border(left=left, right=right, top=top, bottom=bottom)


def _rule(*, last_row: bool, last_year: bool):
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


def _group(subjects: list) -> list[Group]:
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


# ---------------------------------------------------------------- 書き出し

class _SheetWriter:
    """1 シート分を組む。列の位置と行の高さをここで決める。"""

    def __init__(self, sheet, context: Context, department: Department, term: Term):
        self.sheet = sheet
        self.context = context
        self.department = department
        self.term = term
        self.junior = department is Department.JUNIOR
        # **短大は集中を表の下へ置く。** 曜日ブロックが 7 列あり、右へさらに
        # 集中を継ぎ足すと 1 枚に収まらないほど横長になる（大学は 6 列）。
        self.intensive_below = self.junior
        self.years = self._years()
        self.day_start: dict[str, int] = {}
        self.intensive_start = 1
        self._lay_out_columns()

    # -- 下ごしらえ ---------------------------------------------------

    def _years(self) -> list[int]:
        """このシートに出す年次。

        学科ごとに決まっている値（大学 1〜4 年、短大 1〜2 年）を使う。
        ただしデータに想定外の年次があれば足す。**黙って落とさない。**
        配当年次の欄が空だったり読み違えたりしたときに、その科目が
        どこにも出ないまま気づけなくなるのを防ぐ。
        """
        expected = set(DEPARTMENT_YEARS.get(self.department, (1,)))
        found = {s.year for s in self.context.subjects.values()
                 if s.department is self.department}
        return sorted(expected | found)

    def _lay_out_columns(self) -> None:
        column = 3  # A=時限, B=年次
        for day in DAYS:
            self.day_start[day] = column
            for spec in day_columns(self.department, day):
                self.sheet.column_dimensions[get_column_letter(column)].width = spec.width
                column += 1
        self.grid_end = column - 1

        if self.intensive_below:
            self.intensive_start = 1
            self.last_column = self.grid_end
        else:
            self.sheet.column_dimensions[get_column_letter(column)].width = SPACER_WIDTH
            column += 1
            self.intensive_start = column
            self.sheet.column_dimensions[get_column_letter(column)].width = YEAR_COLUMN_WIDTH
            column += 1
            for spec in intensive_columns(self.department):
                self.sheet.column_dimensions[get_column_letter(column)].width = spec.width
                column += 1
            self.last_column = column - 1

        self.sheet.column_dimensions["A"].width = PERIOD_COLUMN_WIDTH
        self.sheet.column_dimensions["B"].width = YEAR_COLUMN_WIDTH

    def _in_cell(self, day: str, period: int, year: int) -> list:
        codes = self.context and self.timetable.occupied_by(TimeSlot(day, period))
        found = []
        for code in codes:
            subject = self.context.subjects.get(code)
            if subject is None:
                continue
            if (subject.department is self.department and subject.term is self.term
                    and subject.year == year):
                found.append(subject)
        return found

    # -- 見出し -------------------------------------------------------

    def _write_heading(self) -> None:
        sheet = self.sheet
        sheet.row_dimensions[TITLE_ROW].height = TITLE_HEIGHT
        sheet.row_dimensions[DAY_ROW].height = DAY_HEIGHT
        sheet.row_dimensions[HEADER_ROW].height = BODY_HEIGHT

        title = sheet.cell(TITLE_ROW, 1,
                           f"{DEPARTMENT_TITLES[self.department]}　{self.term.value}")
        title.font = TITLE_FONT
        title.alignment = Alignment(horizontal="left", vertical="center")
        # 日付は右端へ寄せる。集中を右に置く学科ではその帯の上、下に回す
        # 学科では曜日ブロックの右端になる（A1 には見出しが入っている）。
        stamp_start = (max(2, self.last_column - 3) if self.intensive_below
                       else self.intensive_start)
        stamp = sheet.cell(TITLE_ROW, stamp_start, date.today().strftime("%Y.%m.%d"))
        stamp.font = DATE_FONT
        stamp.alignment = Alignment(horizontal="right", vertical="center", shrink_to_fit=True)
        sheet.merge_cells(start_row=TITLE_ROW, start_column=stamp_start,
                          end_row=TITLE_ROW, end_column=self.last_column)
        for column in range(1, self.last_column + 1):
            sheet.cell(TITLE_ROW, column).border = Border(bottom=MEDIUM)

        # A2:B3 は時限と年次の見出し。文字は入れず、塗りだけ合わせる。
        sheet.merge_cells(start_row=DAY_ROW, start_column=1, end_row=HEADER_ROW, end_column=2)
        for row in (DAY_ROW, HEADER_ROW):
            for column in (1, 2):
                cell = sheet.cell(row, column)
                cell.fill = HEADER_FILL
                cell.border = _frame(left=MEDIUM, right=MEDIUM,
                                     top=MEDIUM if row == DAY_ROW else None,
                                     bottom=MEDIUM if row == HEADER_ROW else None)

        for day in DAYS:
            start = self.day_start[day]
            specs = day_columns(self.department, day)
            self._band(start, len(specs), f"{day}曜日：{self._face(day)}", specs)

        if not self.intensive_below:
            self._band(self.intensive_start,
                       len(intensive_columns(self.department)) + 1,
                       INTENSIVE_HEADING, intensive_columns(self.department),
                       lead_blank=True)

    def _face(self, day: str) -> str:
        """その曜日が対面か遠隔か。

        大学の金曜は遠隔だけ（遠隔列が ○ か × で埋まっていて空欄が無い）。
        短大は × が無く空欄があるため、対面も金曜に来る。
        """
        if day != REMOTE_DAY:
            return "対面"
        return "対面＆遠隔" if self.junior else "遠隔"

    def _band(self, start: int, width: int, heading: str, specs, lead_blank=False) -> None:
        """曜日（または集中）1 ブロック分の 2 行の見出しを書く。"""
        sheet = self.sheet
        end = start + width - 1
        first = start + 1 if lead_blank else start
        cell = sheet.cell(DAY_ROW, first, heading)
        cell.font = DAY_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", shrink_to_fit=True)
        if end > first:
            sheet.merge_cells(start_row=DAY_ROW, start_column=first,
                              end_row=DAY_ROW, end_column=end)
        if lead_blank:
            sheet.merge_cells(start_row=DAY_ROW, start_column=start,
                              end_row=HEADER_ROW, end_column=start)

        for offset in range(width):
            column = start + offset
            for row in (DAY_ROW, HEADER_ROW):
                target = sheet.cell(row, column)
                target.fill = HEADER_FILL
                target.border = _frame(
                    left=MEDIUM if column == start else DOTTED,
                    right=MEDIUM if column == end else DOTTED,
                    top=MEDIUM, bottom=MEDIUM,
                )
        for offset, spec in enumerate(specs):
            column = start + offset + (1 if lead_blank else 0)
            target = sheet.cell(HEADER_ROW, column, spec.title or None)
            target.font = HEADER_FONT
            target.alignment = Alignment(horizontal="center", vertical="center",
                                         shrink_to_fit=True)

    # -- 本体 ---------------------------------------------------------

    def _write_body(self) -> int:
        """時限 × 年次でブロックを積む。最後に使った行を返す。"""
        sheet = self.sheet
        row = FIRST_BODY_ROW
        for period in PERIODS:
            period_start = row
            plan = []
            for year in self.years:
                groups = {day: _group(self._in_cell(day, period, year)) for day in DAYS}
                # そのコマで最も背の高い曜日に合わせる。どの曜日も空なら 1 行。
                height = max(1, max(sum(g.height for g in groups[day]) for day in DAYS))
                plan.append((year, groups, height))

            # 時限の欄に授業時間を 2 段で出すので、その高さを確保する
            shortfall = ROWS_FOR_PERIOD_LABEL - sum(h for _, _, h in plan)
            if shortfall > 0:
                year, groups, height = plan[-1]
                plan[-1] = (year, groups, height + shortfall)

            for index, (year, groups, height) in enumerate(plan):
                last_year = index == len(plan) - 1
                last = row + height - 1
                self._write_year_label(row, last, year, last_year)
                for day in DAYS:
                    self._write_day(day, period, row, last, groups[day], last_year)
                row = last + 1
            self._write_period_label(period_start, row - 1, period)
        return row - 1

    def _write_period_label(self, start: int, end: int, period: int) -> None:
        opens, closes = PERIOD_TIMES[period]
        cell = self.sheet.cell(start, 1, f"{period}時限\n\n{opens}\n〜\n{closes}")
        cell.font = HEADER_FONT
        # 折り返して 2 段で見せる。shrink は wrap に打ち消されるので付けない。
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in range(start, end + 1):
            target = self.sheet.cell(row, 1)
            target.fill = HEADER_FILL
            target.border = _frame(left=MEDIUM, right=MEDIUM,
                                   top=MEDIUM if row == start else None,
                                   bottom=MEDIUM if row == end else None)
        if end > start:
            self.sheet.merge_cells(start_row=start, start_column=1, end_row=end, end_column=1)

    def _write_year_label(self, start: int, end: int, year: int, last_year: bool) -> None:
        cell = self.sheet.cell(start, 2, f"{year}年")
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", shrink_to_fit=True)
        for row in range(start, end + 1):
            target = self.sheet.cell(row, 2)
            target.fill = HEADER_FILL
            target.border = _frame(left=MEDIUM, right=MEDIUM,
                                   bottom=_rule(last_row=row == end, last_year=last_year))
            self.sheet.row_dimensions[row].height = BODY_HEIGHT
        if end > start:
            self.sheet.merge_cells(start_row=start, start_column=2, end_row=end, end_column=2)

    def _write_day(self, day: str, period: int, start: int, end: int,
                   groups: list[Group], last_year: bool) -> None:
        specs = day_columns(self.department, day)
        column_of = {spec.key: self.day_start[day] + i for i, spec in enumerate(specs)}
        block_start = self.day_start[day]
        block_end = block_start + len(specs) - 1
        shade = PatternFill("solid", fgColor=SHADED) if is_shaded(day, period) else None

        for row in range(start, end + 1):
            rule = _rule(last_row=row == end, last_year=last_year)
            for column in range(block_start, block_end + 1):
                cell = self.sheet.cell(row, column)
                cell.border = _frame(
                    left=MEDIUM if column == block_start else DOTTED,
                    right=MEDIUM if column == block_end else DOTTED,
                    bottom=rule,
                )
                if shade is not None:
                    cell.fill = shade

        row = start
        for group in groups:
            self._write_group(group, row, column_of, specs)
            row += group.height

    def _write_group(self, group: Group, start: int, column_of, specs) -> None:
        sheet = self.sheet
        end = start + group.height - 1
        spanning = {"name", "quarter", "required_only", "category"}

        for spec in specs:
            column = column_of[spec.key]
            if spec.key == "teacher":
                for offset, teacher in enumerate(group.teachers):
                    cell = sheet.cell(start + offset, column, teacher or None)
                    cell.font = BODY_FONT
                    cell.alignment = Alignment(horizontal="left", vertical="center",
                                               shrink_to_fit=True)
                continue
            if spec.key not in spanning:
                # 抽選・人数・教室は事務局があとから手で入れる欄。枠だけ用意する。
                if spec.key == "room":
                    sheet.cell(start, column).font = ROOM_FONT
                continue

            value = self._value(spec.key, group)
            cell = sheet.cell(start, column, value or None)
            if spec.key == "name":
                cell.font = BODY_FONT
                # **折り返すのは縦に結合したときだけ。** Excel では wrap が
                # shrink を打ち消す。1 行しかないセルで折り返すと、2 行目が
                # 行高（23.5）に隠れて読めなくなる。見本も、複数行に結合した
                # セルにだけ wrap を付けている。
                cell.alignment = Alignment(horizontal="left", vertical="center",
                                           wrap_text=group.height > 1,
                                           shrink_to_fit=True)
            else:
                cell.font = SMALL_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center",
                                           shrink_to_fit=True)
            if end > start:
                sheet.merge_cells(start_row=start, start_column=column,
                                  end_row=end, end_column=column)

    def _value(self, key: str, group: Group) -> str:
        if key == "name":
            return group.name
        if key == "quarter":
            return group.quarter
        if key == "category":
            return CATEGORY_MARKS.get(group.category, "")
        # 大学の「備考」は見本どおり必修の「必」だけを出す。
        return "必" if group.category is Category.REQUIRED else ""

    # -- 集中講義 -----------------------------------------------------

    def _intensive(self) -> list:
        """このシートに出す集中講義。

        通年の科目は前期・後期のどちらのシートにも出す。年度をまたいで
        開くものなので、片方にだけ載せると、もう片方を見た人が見落とす。
        """
        found = []
        for code in self.intensive_codes:
            subject = self.context.subjects.get(code)
            if subject is None or subject.department is not self.department:
                continue
            if subject.term is self.term or subject.term is Term.FULL_YEAR:
                found.append(subject)
        return found

    def _write_intensive(self) -> int:
        """集中の欄を組む。**科目が尽きたところで太い実線を引いて終わる。**

        グリッド側は 5 時限 × 年次ぶんの高さが必ず要るが、集中はその学科・
        学期にあるだけしか無い。下まで空の枠を伸ばすと、何も無い場所を
        延々と目で追うことになる。
        """
        specs = intensive_columns(self.department)
        year_column = self.intensive_start
        first = year_column + 1
        last = first + len(specs) - 1

        by_year: dict[int, list] = {}
        for subject in self._intensive():
            by_year.setdefault(subject.year, []).append(subject)

        years = sorted(by_year)
        row = FIRST_BODY_ROW
        for index, year in enumerate(years):
            last_year = index == len(years) - 1
            groups = _group(by_year[year])
            end = row + sum(g.height for g in groups) - 1

            label = self.sheet.cell(row, year_column, f"{year}年")
            label.font = HEADER_FONT
            label.alignment = Alignment(horizontal="center", vertical="center",
                                        shrink_to_fit=True)
            for line in range(row, end + 1):
                rule = _rule(last_row=line == end, last_year=last_year)
                cell = self.sheet.cell(line, year_column)
                cell.fill = HEADER_FILL
                cell.border = _frame(left=MEDIUM, right=DOTTED, bottom=rule)
                for column in range(first, last + 1):
                    self.sheet.cell(line, column).border = _frame(
                        left=DOTTED, right=MEDIUM if column == last else DOTTED,
                        bottom=rule,
                    )
                self.sheet.row_dimensions[line].height = BODY_HEIGHT
            if end > row:
                self.sheet.merge_cells(start_row=row, start_column=year_column,
                                       end_row=end, end_column=year_column)

            column_of = {spec.key: first + i for i, spec in enumerate(specs)}
            at = row
            for group in groups:
                self._write_group(group, at, column_of, specs)
                at += group.height
            row = end + 1
        return row - 1

    # -- 集中講義（表の下に置く場合） --------------------------------

    BELOW_SPANS = ((1, 2, "year"), (3, 5, "name"), (6, 7, "teacher"),
                   (8, 8, "room"), (9, 9, "tail"))
    """下に置くときの列の割り当て（開始列, 終了列, 中身）。

    **短大の列幅に合わせてある。** 下へ回すのは短大だけなので、ほかの
    学科の並びは考えていない。大学も下へ回すことになったら、ここを
    学科ごとに分ける必要がある。

    列幅は曜日ブロックのものをそのまま使い、足りないところは横に結合して
    広げる。短大の A〜I は 時限・年次・抽選・人数・科目名・備考・教員・
    教室・必修 の 9 列で、結合すると科目名に 48 文字ぶんの幅が取れる。
    """

    BELOW_TITLES = {"year": "年次", "name": "授業科目名", "teacher": "教員",
                    "room": "教室"}

    @property
    def below_last(self) -> int:
        """下に置いた集中の欄が使う右端の列。

        表の幅いっぱいまで枠を伸ばさない。右側が空の升目で埋まると、
        まだ続きがあるように見えてしまう。
        """
        return self.BELOW_SPANS[-1][1]

    def _write_intensive_below(self, body_end: int) -> int:
        """表の下に 1 行あけて、左端から集中講義を並べる。

        短大は曜日ブロックが 7 列あり、右へさらに集中を継ぎ足すと 1 枚に
        収まらないほど横長になる。下へ回して左端から始める。
        """
        subjects = self._intensive()
        if not subjects:
            return body_end

        tail_title = "必修" if self.junior else "備考"
        head = body_end + 2  # 1 行あける
        self._write_below_heading(head, tail_title)

        by_year: dict[int, list] = {}
        for subject in subjects:
            by_year.setdefault(subject.year, []).append(subject)

        years = sorted(by_year)
        row = head + 2
        for index, year in enumerate(years):
            last_year = index == len(years) - 1
            groups = _group(by_year[year])
            end = row + sum(g.height for g in groups) - 1
            self._write_below_rows(row, end, year, groups, last_year)
            row = end + 1
        return row - 1

    def _write_below_heading(self, row: int, tail_title: str) -> None:
        sheet = self.sheet
        sheet.row_dimensions[row].height = DAY_HEIGHT
        sheet.row_dimensions[row + 1].height = BODY_HEIGHT

        cell = sheet.cell(row, 1, INTENSIVE_HEADING)
        cell.font = DAY_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   shrink_to_fit=True)
        sheet.merge_cells(start_row=row, start_column=1,
                          end_row=row, end_column=self.below_last)
        for column in range(1, self.below_last + 1):
            for line in (row, row + 1):
                target = sheet.cell(line, column)
                target.fill = HEADER_FILL
                target.border = _frame(
                    left=MEDIUM if column == 1 else DOTTED,
                    right=MEDIUM if column == self.below_last else DOTTED,
                    top=MEDIUM, bottom=MEDIUM,
                )
        for start, stop, key in self.BELOW_SPANS:
            title = self.BELOW_TITLES.get(key, tail_title)
            target = sheet.cell(row + 1, start, title)
            target.font = HEADER_FONT
            target.alignment = Alignment(horizontal="center", vertical="center",
                                         shrink_to_fit=True)
            if stop > start:
                sheet.merge_cells(start_row=row + 1, start_column=start,
                                  end_row=row + 1, end_column=stop)

    def _write_below_rows(self, row: int, end: int, year: int, groups, last_year) -> None:
        sheet = self.sheet
        for line in range(row, end + 1):
            rule = _rule(last_row=line == end, last_year=last_year)
            sheet.row_dimensions[line].height = BODY_HEIGHT
            for column in range(1, self.below_last + 1):
                sheet.cell(line, column).border = _frame(
                    left=MEDIUM if column == 1 else DOTTED,
                    right=MEDIUM if column == self.below_last else DOTTED,
                    bottom=rule,
                )
        for line in range(row, end + 1):
            sheet.cell(line, 1).fill = HEADER_FILL
            sheet.cell(line, 2).fill = HEADER_FILL

        label = sheet.cell(row, 1, f"{year}年")
        label.font = HEADER_FONT
        label.alignment = Alignment(horizontal="center", vertical="center",
                                    shrink_to_fit=True)
        sheet.merge_cells(start_row=row, start_column=1, end_row=end, end_column=2)

        at = row
        for group in groups:
            self._write_below_group(group, at, at + group.height - 1)
            at += group.height

    def _write_below_group(self, group: Group, start: int, end: int) -> None:
        sheet = self.sheet
        for first, stop, key in self.BELOW_SPANS:
            if key == "year":
                continue
            if key == "teacher":
                for offset, teacher in enumerate(group.teachers):
                    cell = sheet.cell(start + offset, first, teacher or None)
                    cell.font = BODY_FONT
                    cell.alignment = Alignment(horizontal="left", vertical="center",
                                               shrink_to_fit=True)
                    if stop > first:
                        sheet.merge_cells(start_row=start + offset, start_column=first,
                                          end_row=start + offset, end_column=stop)
                continue
            if key == "room":
                sheet.cell(start, first).font = ROOM_FONT
                continue

            value = group.name if key == "name" else self._value(
                "category" if self.junior else "required_only", group)
            cell = sheet.cell(start, first, value or None)
            if key == "name":
                cell.font = BODY_FONT
                cell.alignment = Alignment(horizontal="left", vertical="center",
                                           wrap_text=group.height > 1,
                                           shrink_to_fit=True)
            else:
                cell.font = SMALL_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center",
                                           shrink_to_fit=True)
            if stop > first or end > start:
                sheet.merge_cells(start_row=start, start_column=first,
                                  end_row=end, end_column=stop)

    def _set_up_printing(self, bottom: int) -> None:
        sheet = self.sheet
        sheet.freeze_panes = sheet.cell(FIRST_BODY_ROW, 3)
        sheet.sheet_view.showGridLines = False
        sheet.sheet_view.zoomScale = ZOOM
        sheet.print_title_rows = f"{TITLE_ROW}:{HEADER_ROW}"
        sheet.print_area = (
            f"A{TITLE_ROW}:{get_column_letter(self.last_column)}{bottom}"
        )
        setup = sheet.page_setup
        setup.paperSize = sheet.PAPERSIZE_A3
        setup.orientation = "landscape"
        # 倍率を決め打ちにしない。科目が増えた年に、右端が黙って切れてしまう。
        setup.fitToWidth = 1
        setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_margins.left = sheet.page_margins.right = 0.2
        sheet.page_margins.top = 0.2
        sheet.page_margins.bottom = 0.1

    def write(self, timetable, intensive_codes) -> None:
        self.timetable = timetable
        self.intensive_codes = list(intensive_codes)
        self._write_heading()
        body_end = self._write_body()
        if self.intensive_below:
            bottom = self._write_intensive_below(body_end)
        else:
            bottom = max(body_end, self._write_intensive())
        self._set_up_printing(bottom)


def write_timetable_excel(context: Context, result, path: str | Path) -> Path:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    for name, department, term in SHEET_PLAN:
        writer = _SheetWriter(workbook.create_sheet(name), context, department, term)
        writer.write(result.timetable, result.intensive_codes)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target
