"""候補の再計算を絞り込む最適化の前提を検証する。

ソルバーは 1 件置くたびに全残科目の候補を作り直すのをやめ、影響を
受ける科目だけを計算し直す。**影響範囲の見積もりが狭すぎると、古い
候補を使って制約違反を作る。** その見積もりが正しいことをここで確かめる。
"""
import pytest

from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets
from app.scheduler.solver import _Index


def _all_counts(context, timetable):
    return {
        code: len(feasible_slot_sets(context, timetable, subject))
        for code, subject in context.subjects.items()
        if not subject.is_intensive
    }


@pytest.mark.parametrize("kind", ["plain", "joint", "pair"])
def test_only_the_estimated_subjects_change(real_context, kind):
    """1 件置いて候補が変わった科目が、見積もりの範囲に収まること。"""
    def pick():
        for code, subject in sorted(real_context.subjects.items()):
            if subject.is_intensive or subject.fixed_slot:
                continue
            if kind == "joint" and subject.joint_id:
                return code
            if kind == "pair" and subject.pair_id:
                return code
            if kind == "plain" and not subject.joint_id and not subject.pair_id:
                return code
        raise AssertionError(f"{kind} に当てはまる科目が実データにない")

    code = pick()
    timetable = Timetable()
    before = _all_counts(real_context, timetable)
    timetable.place(code, (TimeSlot("水", 3),), AssignmentSource.SOLVER)
    after = _all_counts(real_context, timetable)

    changed = {c for c in before if before[c] != after[c]} - {code}
    estimated = _Index(real_context).affected_by(real_context, code)
    assert changed <= estimated, sorted(changed - estimated)


def test_the_estimate_is_not_simply_everything(real_context):
    """全科目を返すだけなら速くならない。実際に絞れていること。"""
    index = _Index(real_context)
    code = next(iter(sorted(real_context.subjects)))
    estimated = index.affected_by(real_context, code)
    assert 0 < len(estimated) < len(real_context.subjects) / 4


def test_adjacent_partner_lookup_matches_a_full_scan(real_context):
    index = _Index(real_context)
    timetable = Timetable()
    seminar = next(
        code for code, s in sorted(real_context.subjects.items()) if s.adjacent_id
    )
    partner = next(
        code for code, s in real_context.subjects.items()
        if s.adjacent_id == real_context.subjects[seminar].adjacent_id and code != seminar
    )
    assert not index.adjacent_partner_placed(real_context, timetable, seminar)
    timetable.place(partner, (TimeSlot("月", 1),), AssignmentSource.SOLVER)
    assert index.adjacent_partner_placed(real_context, timetable, seminar)
