"""生成結果を、事務局が使ってきた様式の Excel として書き出す。

学科 × 学期で 6 シート。曜日を横に並べ、時限と年次で縦に区切る。
**画面のマトリクス表とは別物である。** 画面は 5 日 × 5 限の升目に科目を
積むが、こちらは事務局が長年手で作ってきた紙の形に合わせている。

    行1  経営学科　前期                                    2026.09.29
    行2  月曜日：対面 │ 火曜日：対面 │ … │ 金曜日：遠隔 │ 集中
    行3  抽選│人数│授業科目名│教員│教室│備考
    行4〜 A列=時限（縦結合） B列=年次（縦結合） その下に科目を縦に並べる

**このファイルは「書き込む手順」だけを持つ。** どんな見た目にするか
（列の並び・幅・書体・罫線・網掛け）は sheet_layout.py にある。

書き込みは 1 本の道を通る。曜日ブロックも集中ブロックも「列の範囲
（Span）の並び」として表し、同じ _frame_rows・_write_band・_write_group
が書く。以前は集中だけ別処理を持っており、片方を直してもう片方を直し
忘れる取りこぼしが起きた。

**教室・抽選・人数は空欄で出す。** カリキュラム一覧にその列が無く、
埋める元が無い。見本のシート名が「教室入」であることからも、ここは
事務局があとから手で入れる欄である。枠だけ用意して渡す。

**教員名は Excel の元の表記で書く。** 突合には空白を落とした正規化済みの
氏名を使うが、紙に出すのは「築　雅之」のように全角空白で姓名を分けた形に
する。カリキュラム一覧の 97% がその形で、事務局が長年そう作ってきた。
"""
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, PatternFill
from openpyxl.utils import get_column_letter

from app.constraints.context import Context
from app.export.sheet_layout import (
    BODY_FONT, BODY_HEIGHT, CATEGORY, CATEGORY_MARKS, DATE_FONT, DAY_FONT,
    DAY_HEIGHT, DAY_ROW, DEPARTMENT_TITLES, DEPARTMENT_YEARS, DOTTED,
    FIRST_BODY_ROW, HEADER_FILL, HEADER_FONT, HEADER_ROW, INTENSIVE_HEADING,
    MEDIUM, PERIOD_COLUMN_WIDTH, PERIOD_TIMES, REMOTE_DAY, REQUIRED_ONLY,
    ROOM_FONT, ROWS_FOR_PERIOD_LABEL, SHADED, SHEET_PLAN, SMALL_FONT,
    SPACER_WIDTH, SPANNING_KEYS, TITLE_FONT, TITLE_HEIGHT, TITLE_ROW, ZOOM,
    YEAR_COLUMN_WIDTH, Group, Span,
    day_columns, frame, group_subjects, intensive_columns, is_shaded, row_rule,
)
from app.models.enums import Category, Department, Term
from app.models.timeslot import DAYS, PERIODS, TimeSlot

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
                cell.border = frame(left=MEDIUM, right=MEDIUM,
                                     top=MEDIUM if row == DAY_ROW else None,
                                     bottom=MEDIUM if row == HEADER_ROW else None)

        for day in DAYS:
            self._write_band(DAY_ROW, self._day_spans(day),
                             f"{day}曜日：{self._face(day)}", year_inside=True)

        if not self.intensive_below:
            # 右に置く集中は、曜日と同じ帯に並べる
            self._write_band(DAY_ROW, self._intensive_spans(),
                             INTENSIVE_HEADING, year_inside=False)

    def _face(self, day: str) -> str:
        """その曜日が対面か遠隔か。

        大学の金曜は遠隔だけ（遠隔列が ○ か × で埋まっていて空欄が無い）。
        短大は × が無く空欄があるため、対面も金曜に来る。
        """
        if day != REMOTE_DAY:
            return "対面"
        return "対面＆遠隔" if self.junior else "遠隔"

    def _day_spans(self, day: str) -> list[Span]:
        """曜日ブロックの列取り。1 項目 1 列で足りる。"""
        start = self.day_start[day]
        return [Span(start + offset, start + offset, spec.key, spec.title)
                for offset, spec in enumerate(day_columns(self.department, day))]

    # -- 本体 ---------------------------------------------------------

    def _write_body(self) -> int:
        """時限 × 年次でブロックを積む。最後に使った行を返す。"""
        sheet = self.sheet
        row = FIRST_BODY_ROW
        for period in PERIODS:
            period_start = row
            plan = []
            for year in self.years:
                groups = {day: group_subjects(self._in_cell(day, period, year)) for day in DAYS}
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
            target.border = frame(left=MEDIUM, right=MEDIUM,
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
            target.border = frame(left=MEDIUM, right=MEDIUM,
                                   bottom=row_rule(last_row=row == end, last_year=last_year))
            self.sheet.row_dimensions[row].height = BODY_HEIGHT
        if end > start:
            self.sheet.merge_cells(start_row=start, start_column=2, end_row=end, end_column=2)

    def _write_day(self, day: str, period: int, start: int, end: int,
                   groups: list[Group], last_year: bool) -> None:
        spans = self._day_spans(day)
        self._frame_rows(spans, start, end, last_year=last_year,
                         shade=PatternFill("solid", fgColor=SHADED)
                         if is_shaded(day, period) else None)
        row = start
        for group in groups:
            self._writegroup_subjects(group, row, spans)
            row += group.height

    def _writegroup_subjects(self, group: Group, start: int, spans: list[Span]) -> None:
        """同じ科目名のひとかたまりを書く。

        科目名は 1 回だけ書いて教員の人数ぶん縦に結合し、教員はその行数
        ぶん 1 行ずつ並べる。抽選・人数・教室は事務局があとから手で入れる
        欄なので、枠だけ用意して空のままにする。
        """
        end = start + group.height - 1

        for span in spans:
            if span.key == "teacher":
                self._write_teachers(group, start, span)
            elif span.key == "room":
                # 空欄だが、事務局が教室番号を打ったときの大きさを決めておく
                self.sheet.cell(start, span.first).font = ROOM_FONT
                self._merge(start, start, span)
            elif span.key in SPANNING_KEYS:
                self._write_spanning(group, start, end, span)

    def _write_teachers(self, group: Group, start: int, span: Span) -> None:
        for offset, teacher in enumerate(group.teachers):
            row = start + offset
            cell = self.sheet.cell(row, span.first, teacher or None)
            cell.font = BODY_FONT
            cell.alignment = Alignment(horizontal="left", vertical="center",
                                       shrink_to_fit=True)
            self._merge(row, row, span)

    def _write_spanning(self, group: Group, start: int, end: int, span: Span) -> None:
        """教員の人数ぶん縦に結合して 1 回だけ書く項目（科目名・開講期・区分）。"""
        cell = self.sheet.cell(start, span.first, self._value(span.key, group) or None)
        if span.key == "name":
            cell.font = BODY_FONT
            # **折り返すのは縦に結合したときだけ。** Excel では wrap が
            # shrink を打ち消す。1 行しかないセルで折り返すと、2 行目が
            # 行高（23.5）に隠れて読めなくなる。見本も、複数行に結合した
            # セルにだけ wrap を付けている。
            cell.alignment = Alignment(horizontal="left", vertical="center",
                                       wrap_text=group.height > 1, shrink_to_fit=True)
        else:
            cell.font = SMALL_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center",
                                       shrink_to_fit=True)
        self._merge(start, end, span)

    def _merge(self, start: int, end: int, span: Span) -> None:
        """1 セルだけの結合は書かない。

        openpyxl は止めずに <mergeCell ref="B2"/> を書き出すが、結合は
        2 セル以上を束ねるものなので仕様から外れており、Excel が修復を
        促すことがある。
        """
        if end > start or span.merged:
            self.sheet.merge_cells(start_row=start, start_column=span.first,
                                   end_row=end, end_column=span.last)

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

    BELOW_START = 2
    """表の下へ回すとき、集中の欄が始まる列。

    **A 列を 1 つあける。** 左端にぴったり寄せると、上の表の時限の列と
    縦につながって見え、集中が時間割の続きのように読めてしまう。1 列
    あけるだけで別の塊だと分かる。
    """

    BELOW_SPANS = ((0, 0, "year"), (1, 3, "name"), (4, 5, "teacher"),
                   (6, 6, "room"), (7, 7, "tail"))
    """表の下へ回すときの列の割り当て（BELOW_START からの位置, 同終わり, 中身）。

    **短大の列幅に合わせてある。** 下へ回すのは短大だけなので、ほかの
    学科の並びは考えていない。大学も下へ回すことになったら、ここを
    学科ごとに分ける必要がある。

    列幅は曜日ブロックのものをそのまま使い、足りないところは横に結合して
    広げる。**広げるのは、結合しないと入らないものだけ。** 年次・教室・
    必修は上の表で同じものが入っている列の幅で足りている。どれか 1 つ
    だけ広いと、そこが間延びして見える。

        B     年次       5.6
        C:E   授業科目名 48.6（抽選・人数・科目名を結合）
        F:G   教員       22.6（備考・教員を結合）
        H     教室       10.6
        I     必修        6.5
    """

    INTENSIVE_TITLES = {"year": "年次", "name": "授業科目名",
                        "teacher": "教員", "room": "教室"}

    def _intensive_spans(self) -> list[Span]:
        """集中の欄の列取り。置き場所が学科で違う。

        大学は曜日ブロックが 6 列で右に余地があるので、表の右へ置く。
        短大は 7 列あり、右へ継ぎ足すと 1 枚に収まらないほど横長になる
        ので表の下へ回す。**どちらも「列の範囲の並び」として同じ形で
        表せるので、書き込む処理は 1 本で足りる。**
        """
        # 末尾の欄は学科で意味が違う。短大は必・選必を書き分け、大学は
        # 見本どおり必修の「必」だけを出す。どちらを書くかは列の名前で
        # 決まる（内訳は _value が持つ）ので、ここで本来の名前に直す。
        tail = CATEGORY if self.junior else REQUIRED_ONLY
        title = {**self.INTENSIVE_TITLES, tail.key: tail.title}
        named = {**{k: k for k in title}, "tail": tail.key}

        if self.intensive_below:
            return [Span(self.BELOW_START + first, self.BELOW_START + last,
                         named[key], title[named[key]])
                    for first, last, key in self.BELOW_SPANS]

        # 右に置くときは 1 項目 1 列。年次の欄には見出しを置かない
        # （見本の AG2:AG3 が空欄で、「集中」は 1 つ右から始まる）。
        column = self.intensive_start
        spans = [Span(column, column, "year", "")]
        for offset, spec in enumerate(intensive_columns(self.department), start=1):
            spans.append(Span(column + offset, column + offset, spec.key,
                              title[spec.key]))
        return spans

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

    def _write_intensive(self, body_end: int) -> int:
        """集中の欄を組み、最後に使った行を返す。

        **科目が尽きたところで太い実線を引いて終わる。** グリッド側は
        5 時限 × 年次ぶんの高さが必ず要るが、集中はその学科・学期に
        あるだけしか無い。下まで空の枠を伸ばすと、何も無い場所を延々と
        目で追うことになる。
        """
        subjects = self._intensive()
        spans = self._intensive_spans()

        if self.intensive_below:
            if not subjects:
                return body_end
            head = body_end + 2  # 表とのあいだを 1 行あける
            self._write_band(head, spans, INTENSIVE_HEADING, year_inside=True)
            row = head + 2
        else:
            row = FIRST_BODY_ROW  # 見出しは曜日と同じ帯に並べて済んでいる

        by_year: dict[int, list] = {}
        for subject in subjects:
            by_year.setdefault(subject.year, []).append(subject)

        years = sorted(by_year)
        for index, year in enumerate(years):
            groups = group_subjects(by_year[year])
            end = row + sum(g.height for g in groups) - 1
            self._write_year_rows(spans, row, end, year, groups,
                                  last_year=index == len(years) - 1)
            row = end + 1
        return row - 1

    def _write_year_rows(self, spans: list[Span], start: int, end: int, year: int,
                         groups: list[Group], last_year: bool) -> None:
        """集中の 1 年次ぶん。年次の欄を縦に結合し、その右へ科目を並べる。"""
        year_span = spans[0]
        self._frame_rows(spans, start, end, last_year=last_year,
                         filled={year_span.key})

        label = self.sheet.cell(start, year_span.first, f"{year}年")
        label.font = HEADER_FONT
        label.alignment = Alignment(horizontal="center", vertical="center",
                                    shrink_to_fit=True)
        self._merge(start, end, year_span)

        row = start
        for group in groups:
            self._writegroup_subjects(group, row, spans[1:])
            row += group.height

    # -- 枠と見出し ---------------------------------------------------

    def _frame_rows(self, spans: list[Span], start: int, end: int, *,
                    last_year: bool, filled: set[str] = frozenset(),
                    shade: PatternFill | None = None) -> None:
        """ブロックの罫線と塗りを敷く。

        左右の端は太い実線、内側は点線。下の線は _rule が決める
        （時限のあいだは太い実線、年次のあいだは点線、年次の中は線なし）。
        """
        left, right = spans[0].first, spans[-1].last
        for row in range(start, end + 1):
            rule = row_rule(last_row=row == end, last_year=last_year)
            self.sheet.row_dimensions[row].height = BODY_HEIGHT
            for span in spans:
                for column in range(span.first, span.last + 1):
                    cell = self.sheet.cell(row, column)
                    cell.border = frame(
                        left=MEDIUM if column == left else DOTTED,
                        right=MEDIUM if column == right else DOTTED,
                        bottom=rule,
                    )
                    if span.key in filled:
                        cell.fill = HEADER_FILL
                    elif shade is not None:
                        cell.fill = shade

    def _write_band(self, row: int, spans: list[Span], heading: str, *,
                    year_inside: bool) -> None:
        """ブロックの 2 行の見出し（帯 ＋ 列名）を書く。

        `year_inside` は年次の列を帯に含めるかどうか。表の下へ回した集中は
        含めて「年次」と書くが、右に置くときは見本に合わせて空欄のまま
        縦に結合する（見本の AG2:AG3）。
        """
        sheet = self.sheet
        sheet.row_dimensions[row].height = DAY_HEIGHT
        sheet.row_dimensions[row + 1].height = BODY_HEIGHT

        titled = spans if year_inside else spans[1:]
        left, right = spans[0].first, spans[-1].last

        cell = sheet.cell(row, titled[0].first, heading)
        cell.font = DAY_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   shrink_to_fit=True)
        if right > titled[0].first:
            sheet.merge_cells(start_row=row, start_column=titled[0].first,
                              end_row=row, end_column=right)
        if not year_inside:
            sheet.merge_cells(start_row=row, start_column=left,
                              end_row=row + 1, end_column=left)

        for column in range(left, right + 1):
            for line in (row, row + 1):
                target = sheet.cell(line, column)
                target.fill = HEADER_FILL
                target.border = frame(
                    left=MEDIUM if column == left else DOTTED,
                    right=MEDIUM if column == right else DOTTED,
                    top=MEDIUM, bottom=MEDIUM,
                )
        for span in titled:
            target = sheet.cell(row + 1, span.first, span.title or None)
            target.font = HEADER_FONT
            target.alignment = Alignment(horizontal="center", vertical="center",
                                         shrink_to_fit=True)
            if span.merged:
                sheet.merge_cells(start_row=row + 1, start_column=span.first,
                                  end_row=row + 1, end_column=span.last)

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
        """1 シート分を組む。見出し → 本体 → 集中 → 印刷設定 の順。"""
        self.timetable = timetable
        self.intensive_codes = list(intensive_codes)
        self._write_heading()
        body_end = self._write_body()
        intensive_end = self._write_intensive(body_end)
        self._set_up_printing(max(body_end, intensive_end))


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
