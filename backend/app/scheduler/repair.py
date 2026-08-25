"""Stage 5.5: 置いたあとに、良くなる移動を探して適用する。

ソルバーは 1 科目ずつ確定させるため、後から見ると惜しい配置が残る。
ここでは**制約を満たす移動しか行わない**ので、配置済みの科目が
未配置に戻ることはない。重みがすべて 0 なら何も動かさない。

合同科目と前後期の対応科目はまとめて動かす。片方だけ動かすと H4 か
H12 に必ず触れるため、`linked_group` 単位で扱う。

**順位付けは影響範囲だけを数える。** 候補コマごとに時間割全体を
計測すると、613 科目 × 25 コマ × 全走査で現実的な時間に終わらない。
1 つの科目群を動かして値が変わるのは、その科目の学科×年次×学期、
担当教員、隣接相手だけである。他は動かないので比較の際に相殺される。
"""
import collections
import time

from app.constraints.context import Context
from app.constraints.linking import linked_group
from app.constraints.validator import check_placement
from app.logging.session_logger import SessionLogger
from app.models.enums import Category
from app.models.timeslot import TimeSlot
from app.models.timetable import Assignment, AssignmentSource, Timetable
from app.scheduler.candidates import candidate_slot_sets
from app.scheduler.objectives import (
    LATE_PERIOD,
    PREFER_EARLY_DEPARTMENTS,
    Snapshot,
    Weights,
    _runs_gap,
    measure,
)

EFFORT_SECONDS = {"off": 0.0, "short": 5.0, "long": 60.0}
"""修復にかける時間の上限。事務局が生成画面で選ぶ。"""

MAX_PASSES = 20
"""時間割全体を見直す回数の上限。時間の上限より先に来ることは稀。"""


class _Neighbourhood:
    """科目群を動かしたときに値が変わる範囲を引く索引。"""

    def __init__(self, context: Context) -> None:
        self.cohort: dict[tuple, list[str]] = collections.defaultdict(list)
        self.teacher: dict[tuple, list[str]] = collections.defaultdict(list)
        self.adjacent: dict[str, list[str]] = collections.defaultdict(list)
        for code, subject in context.subjects.items():
            if subject.category is Category.REQUIRED:
                self.cohort[(subject.department, subject.year, subject.term)].append(code)
            if subject.teacher:
                self.teacher[(subject.teacher, subject.term)].append(code)
            if subject.adjacent_id:
                self.adjacent[subject.adjacent_id].append(code)

    def keys_for(self, context: Context, group: list[str]) -> tuple[set, set, set]:
        cohorts, teachers, adjacent = set(), set(), set()
        for code in group:
            subject = context.subjects[code]
            if subject.category is Category.REQUIRED:
                cohorts.add((subject.department, subject.year, subject.term))
            if subject.teacher:
                teachers.add((subject.teacher, subject.term))
            if subject.adjacent_id:
                adjacent.add(subject.adjacent_id)
        return cohorts, teachers, adjacent

    def _gaps(self, timetable: Timetable, codes: list[str]) -> int:
        by_day: dict[str, set[int]] = collections.defaultdict(set)
        for code in codes:
            for slot in timetable.slot_of(code):
                by_day[slot.day].add(slot.period)
        return sum(_runs_gap(periods) for periods in by_day.values())

    def _days(self, timetable: Timetable, codes: list[str]) -> int:
        return len({slot.day for code in codes for slot in timetable.slot_of(code)})

    def score(
        self, context: Context, timetable: Timetable, keys: tuple, group: list[str],
        weights: Weights,
    ) -> float:
        cohorts, teachers, adjacent = keys
        total = 0.0
        for key in cohorts:
            codes = self.cohort[key]
            total += weights.student_gaps * self._gaps(timetable, codes)
            total += weights.student_days * self._days(timetable, codes)
        for key in teachers:
            total += weights.teacher_gaps * self._gaps(timetable, self.teacher[key])
        for code in group:
            subject = context.subjects[code]
            if subject.department in PREFER_EARLY_DEPARTMENTS:
                total += weights.early_periods * sum(
                    1 for slot in timetable.slot_of(code) if slot.period == LATE_PERIOD
                )
        for key in adjacent:
            placed = [timetable.slot_of(c) for c in self.adjacent[key]]
            if len(placed) == 2 and all(placed):
                a, b = placed[0][0], placed[1][0]
                if a.day != b.day or abs(a.period - b.period) != 1:
                    total += weights.seminar_adjacency
        return total


def _place_all(timetable: Timetable, placed: dict[str, Assignment]) -> None:
    for code, assignment in placed.items():
        timetable.place(code, assignment.slots, assignment.source)


def _try_at(
    context: Context, timetable: Timetable, group: list[str], slots: tuple[TimeSlot, ...]
) -> bool:
    """グループ全員を slots へ置けたら True。置けなければ何も変えない。"""
    if not all(
        not check_placement(context, timetable, context.subjects[code], slots)
        for code in group
    ):
        return False
    for code in group:
        timetable.place(code, slots, AssignmentSource.SOLVER)
    return True


def _movable_groups(context: Context, timetable: Timetable) -> list[list[str]]:
    seen: set[str] = set()
    groups: list[list[str]] = []
    for code in sorted(timetable.assignments):
        if code in seen:
            continue
        group = [c for c in linked_group(context, context.subjects[code])
                 if timetable.is_placed(c)]
        seen.update(group)
        # 事務局が曜日時限を決めた枠は動かさない
        if any(context.subjects[c].fixed_slot is not None for c in group):
            continue
        groups.append(group)
    return groups


def repair(
    context: Context,
    timetable: Timetable,
    weights: Weights,
    *,
    seconds: float,
    logger: SessionLogger | None = None,
) -> Snapshot:
    """良くなる移動を適用し、最終的な計測値を返す。"""
    before = measure(context, timetable)
    if weights.is_idle or seconds <= 0:
        return before

    deadline = time.monotonic() + seconds
    index = _Neighbourhood(context)
    groups = _movable_groups(context, timetable)
    moves = 0

    for _ in range(MAX_PASSES):
        improved = False
        for group in groups:
            if time.monotonic() > deadline:
                break
            keys = index.keys_for(context, group)
            placed = {code: timetable.assignments[code] for code in group
                      if timetable.is_placed(code)}
            if not placed:
                continue
            original = next(iter(placed.values())).slots
            base = index.score(context, timetable, keys, group, weights)

            for code in placed:
                timetable.remove(code)

            best_slots, best_score = original, base
            for slots in candidate_slot_sets(context.subjects[group[0]]):
                if slots == original or not _try_at(context, timetable, group, slots):
                    continue
                score = index.score(context, timetable, keys, group, weights)
                for code in group:
                    timetable.remove(code)
                if score < best_score:
                    best_slots, best_score = slots, score

            if best_slots != original and _try_at(context, timetable, group, best_slots):
                improved, moves = True, moves + 1
            else:
                _place_all(timetable, placed)

        if not improved or time.monotonic() > deadline:
            break

    after = measure(context, timetable)
    if logger is not None:
        logger.info(
            f"修復: {moves} 件を動かしました"
            f"（学生の空きコマ {before.student_gaps}→{after.student_gaps}、"
            f"登校日 {before.student_days}→{after.student_days}、"
            f"教員の空きコマ {before.teacher_gaps}→{after.teacher_gaps}、"
            f"5 限 {before.late_periods}→{after.late_periods}、"
            f"ゼミ非隣接 {before.seminars_apart}→{after.seminars_apart}）",
            stage="Stage 5.5",
        )
    return after
