"""時間割の「良さ」の計測。制約ではなく好みである。

計測の単位は学期ではなく**クオーター区間**である。制約側は §5.4 の
`active_quarters` で厳密に判定しているのに、好みの計測だけが前①と前②を
同時開講として数えていた。学生も教員も、実際には走っていない 2 コマの
間を「空きコマ」として体験しない。
"""
from app.constraints.context import Context
from app.models.enums import Category, Quarter
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.objectives import measure
from tests.factories import subject as make


def build(subjects):
    return Context.from_lists(subjects, [])


def place(tt, code, day, period):
    tt.place(code, (TimeSlot(day, period),), AssignmentSource.SOLVER)


def test_two_quarters_that_never_coexist_are_not_a_student_gap():
    """前①の月1 と前②の月3 の間に、学生が空くコマは存在しない。"""
    ctx = build([
        make("A1", quarter=Quarter.Q1, teacher="教員甲"),
        make("A2", quarter=Quarter.Q2, teacher="教員乙"),
    ])
    tt = Timetable()
    place(tt, "A1", "月", 1)
    place(tt, "A2", "月", 3)

    assert measure(ctx, tt).student_gaps == 0


def test_a_gap_inside_one_quarter_still_counts():
    """区間で切っても、実際に重なる科目の空きコマは数える。

    前期の科目は前①と前②の両方を走るため 2 区間ぶん数えられるが、
    QUARTERS_PER_TERM で割って学期あたりに戻すので、クオーター科目が
    無い場面の値は学期単位で数えていた頃と変わらない。
    """
    ctx = build([make("A1", teacher="教員甲"), make("A2", teacher="教員乙")])
    tt = Timetable()
    place(tt, "A1", "月", 1)
    place(tt, "A2", "月", 3)

    assert measure(ctx, tt).student_gaps == 1


def test_two_quarters_that_never_coexist_are_not_a_teacher_gap():
    """教員側も同じ。選択科目にしてコホート側の計測から外す。"""
    ctx = build([
        make("A1", quarter=Quarter.Q1, teacher="教員甲", category=Category.ELECTIVE),
        make("A2", quarter=Quarter.Q2, teacher="教員甲", category=Category.ELECTIVE),
    ])
    tt = Timetable()
    place(tt, "A1", "月", 1)
    place(tt, "A2", "月", 3)

    assert measure(ctx, tt).teacher_gaps == 0
