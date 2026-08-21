"""科目 1 件が取り得るコマ集合を列挙する。

構造だけを見る candidate_slot_sets と、制約検証を通した
feasible_slot_sets の 2 段構えにしている。前者は科目ごとに一度
計算すれば使い回せるため、探索の内側で再計算しない。
"""
from itertools import combinations

from app.constraints.context import Context
from app.constraints.validator import is_allowed
from app.models.subject import Subject
from app.models.timeslot import DAYS, PERIODS, TimeSlot
from app.models.timetable import Timetable


def candidate_slot_sets(subject: Subject) -> list[tuple[TimeSlot, ...]]:
    """制約を見ずに、コマ数と連続要件だけから候補を列挙する。"""
    if subject.is_intensive:
        return []
    if subject.fixed_slot is not None:
        return [tuple(subject.fixed_slot)]

    all_slots = [TimeSlot(day, period) for day in DAYS for period in PERIODS]

    if subject.slots_required == 1:
        return [(slot,) for slot in all_slots]

    if subject.requires_consecutive:
        result: list[tuple[TimeSlot, ...]] = []
        for day in DAYS:
            for start in PERIODS[: len(PERIODS) - subject.slots_required + 1]:
                result.append(tuple(
                    TimeSlot(day, start + offset)
                    for offset in range(subject.slots_required)
                ))
        return result

    return [tuple(combo) for combo in combinations(all_slots, subject.slots_required)]


def feasible_slot_sets(
    context: Context,
    timetable: Timetable,
    subject: Subject,
    structural: list[tuple[TimeSlot, ...]] | None = None,
) -> list[tuple[TimeSlot, ...]]:
    """現在の配置状況で実際に置ける候補だけを返す。

    structural には candidate_slot_sets の結果を渡せる。同じ科目を何度も
    評価する探索では、構造だけで決まる候補を作り直す意味がない。
    """
    if structural is None:
        structural = candidate_slot_sets(subject)
    return [
        slots for slots in structural
        if is_allowed(context, timetable, subject, slots)
    ]
