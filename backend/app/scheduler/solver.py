"""Stage 5: 最小残余値ヒューリスティックによる決定的な貪欲配置。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
候補の少ない科目から順に確定させ、置けない科目は未配置として記録して
先へ進む。必ず有限時間で終わり、部分解を返す。
"""
from app.constraints.context import Context
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets
from app.scheduler.preference import best_option

DEFAULT_NODE_LIMIT = 200_000


def solve(
    context: Context,
    timetable: Timetable,
    codes: list[str],
    *,
    node_limit: int = DEFAULT_NODE_LIMIT,
) -> list[str]:
    """codes を timetable に配置し、置けなかったコードを返す。

    既存の配置は動かさない。毎回「候補が最も少ない科目」を選んで確定
    させるため、出勤可能コマが 1 つしかない非常勤の科目などが先に決まる。
    置く場所は候補のうち最も望ましいコマを選ぶ（preference.placement_preference 参照）。
    候補が 1 つも無い科目は未配置として記録し、残りの処理を続ける。
    反復回数が node_limit に達した場合は、そこまでの結果を返す。
    """
    targets = [
        code for code in codes
        if code in context.subjects
        and not context.subjects[code].is_intensive
        and not timetable.is_placed(code)
    ]

    unplaced: list[str] = []
    remaining = list(targets)
    steps = 0

    while remaining and steps < node_limit:
        steps += 1
        options_by_code = {
            code: feasible_slot_sets(context, timetable, context.subjects[code])
            for code in remaining
        }
        # 候補数が同じ場合は授業コード順にして結果を決定的にする
        code = min(remaining, key=lambda c: (len(options_by_code[c]), c))
        remaining.remove(code)

        options = options_by_code[code]
        if not options:
            unplaced.append(code)
            continue
        timetable.place(
            code, best_option(timetable, context.subjects[code], options),
            AssignmentSource.SOLVER,
        )

    unplaced.extend(remaining)
    return unplaced
