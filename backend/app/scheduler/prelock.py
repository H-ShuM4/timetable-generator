"""Stage 1: Python だけで決定的に配置できる科目を確定させる。

ここで確定した配置は Gemini に渡らず、占有済みマップとしてのみ
参照される。トークン削減と、確定枠が動かされないことの保証を兼ねる。
"""
from app.constraints.context import Context
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets


def _is_part_time_with_availability(context: Context, subject: Subject) -> bool:
    teacher = context.teachers.get(subject.teacher)
    return (
        teacher is not None
        and teacher.kind is TeacherKind.PART_TIME
        and bool(teacher.available_slots)
    )


def prelock(
    context: Context,
    subjects: list[Subject],
    *,
    prefer: dict[str, tuple[TimeSlot, ...]] | None = None,
) -> tuple[Timetable, list[str]]:
    """確定枠と非常勤の担当科目を配置し、置けなかったコードを返す。

    特任教員は曜日しか定まらないため対象外とし、Stage 2〜4 に委ねる。

    `prefer` は「置けるならこのコマにしたい」という希望（踏襲モードが
    前年度の配置を渡す）。**候補に残っているものしか選ばない**ので、制約は
    従来どおり全部通る。希望が候補に無ければこれまでどおり候補の先頭を取る。

    これが無いと、事前ロックは候補の先頭＝月曜 1 限寄りを機械的に取るため
    前年度と別のコマを選びやすい。この仕組みを入れる前は、事前ロックした
    非常勤の科目のうち 54 件が前年度と別のコマへ動き、そのコマに前年度から
    いた 11 件を押し出していた（当時の実データでの計測）。
    """
    timetable = Timetable()
    unplaced: list[str] = []

    targets = [s for s in subjects if not s.is_intensive]

    for subject in [s for s in targets if s.fixed_slot is not None]:
        timetable.place(subject.code, tuple(subject.fixed_slot), AssignmentSource.PRELOCK)

    part_time = [
        s for s in targets
        if s.fixed_slot is None and _is_part_time_with_availability(context, s)
    ]
    # 候補が少ない科目から確定させる（最小残余値ヒューリスティック）
    part_time.sort(key=lambda s: len(feasible_slot_sets(context, timetable, s)))

    for subject in part_time:
        options = feasible_slot_sets(context, timetable, subject)
        if not options:
            unplaced.append(subject.code)
            continue
        wanted = (prefer or {}).get(subject.code)
        chosen = wanted if wanted in options else options[0]
        timetable.place(subject.code, chosen, AssignmentSource.PRELOCK)

    return timetable, unplaced
