"""同じコマに入るべき科目を、ソルバーがまとめて確定させること。"""
from app.constraints.context import Context
from app.constraints.linking import linked_group
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.solver import solve


def make(code, term, teacher="教員甲", pair_id=None, joint_id=None,
         department=Department.MANAGEMENT, year=1, name=None):
    return Subject(
        code=code, name=name or code, base_name=name or code, department=department,
        year=year, term=term, quarter=None, category=Category.REQUIRED,
        teacher=teacher, pair_id=pair_id, joint_id=joint_id,
    )


def test_linked_group_walks_joint_and_pair_together():
    subjects = [
        make("B1", Term.SPRING, pair_id="P1", joint_id="J1"),
        make("A1", Term.SPRING, joint_id="J1", department=Department.ACCOUNTING),
        make("B2", Term.FALL, pair_id="P1", joint_id="J2"),
        make("A2", Term.FALL, joint_id="J2", department=Department.ACCOUNTING),
        make("X1", Term.SPRING),
    ]
    ctx = Context.from_lists(subjects, [])
    assert linked_group(ctx, ctx.subjects["B1"]) == ["A1", "A2", "B1", "B2"]
    assert linked_group(ctx, ctx.subjects["X1"]) == ["X1"]


def _fill(ctx, tt, slot, term, *, year=1, count=1):
    """slot を term の必修で埋める。year を変えれば H2 は効かない。"""
    for index in range(count):
        code = f"X{slot.day}{slot.period}{term.value}{year}{index}"
        ctx.subjects[code] = make(code, term, teacher=f"教員{code}", year=year)
        tt.place(code, (slot,), AssignmentSource.PRELOCK)


def _pair_in_a_trap():
    """前期が先に選ばれ、素直に選ぶと後期が詰む盤面を作る。

    月1 は前期だけ空き（後期は必修で埋まっている）、月2 は両学期とも
    空くが混んでいる。好みは空いているコマを選ぶので、先読みが無ければ
    前期は月1 を選び、後期は H12 で月1 に縛られて置けなくなる。

    候補数は前期 2 個・後期 3 個。最小残余値ヒューリスティックが前期を
    先に選ぶようにするためで、実データの日本語リテラシーと同じ順序になる。
    """
    spring = make("S1", Term.SPRING, pair_id="P1", name="対応科目Ⅰ")
    fall = make("F1", Term.FALL, pair_id="P1", name="対応科目Ⅱ")
    ctx = Context.from_lists([spring, fall], [])
    tt = Timetable()

    for day in "火水木金":
        for period in range(1, 6):
            for term in (Term.SPRING, Term.FALL):
                _fill(ctx, tt, TimeSlot(day, period), term)
    for term in (Term.SPRING, Term.FALL):
        _fill(ctx, tt, TimeSlot("月", 5), term)

    _fill(ctx, tt, TimeSlot("月", 1), Term.FALL)                 # 後期だけ塞ぐ
    _fill(ctx, tt, TimeSlot("月", 2), Term.SPRING, year=2, count=2)  # 空くが混雑
    _fill(ctx, tt, TimeSlot("月", 3), Term.SPRING)               # 前期だけ塞ぐ
    _fill(ctx, tt, TimeSlot("月", 4), Term.SPRING)               # 前期だけ塞ぐ
    return ctx, tt


def test_the_trap_really_traps_without_lookahead():
    """盤面の前提確認。前期を単独で置くと月1 が選ばれる。"""
    from app.scheduler.candidates import feasible_slot_sets
    from app.scheduler.preference import best_option

    ctx, tt = _pair_in_a_trap()
    spring_options = feasible_slot_sets(ctx, tt, ctx.subjects["S1"])
    fall_options = feasible_slot_sets(ctx, tt, ctx.subjects["F1"])
    assert len(spring_options) == 2 and len(fall_options) == 3
    assert best_option(tt, ctx.subjects["S1"], spring_options, ctx) == (TimeSlot("月", 1),)


def test_a_pair_avoids_a_slot_the_partner_cannot_use():
    ctx, tt = _pair_in_a_trap()
    assert solve(ctx, tt, ["S1", "F1"]) == []
    assert tt.slot_of("S1") == (TimeSlot("月", 2),)
    assert tt.slot_of("F1") == (TimeSlot("月", 2),)


def test_a_pair_with_no_shared_slot_still_places_one_side():
    """全員が入れるコマが無くても、置けるほうは置く。"""
    spring = make("S1", Term.SPRING, pair_id="P1")
    fall = make("F1", Term.FALL, pair_id="P1")
    ctx = Context.from_lists([spring, fall], [])
    tt = Timetable()
    for day in "月火水木金":
        for period in range(1, 6):
            _fill(ctx, tt, TimeSlot(day, period), Term.FALL)
            if not (day == "月" and period == 1):
                _fill(ctx, tt, TimeSlot(day, period), Term.SPRING)

    assert solve(ctx, tt, ["S1", "F1"]) == ["F1"]
    assert tt.slot_of("S1") == (TimeSlot("月", 1),)
