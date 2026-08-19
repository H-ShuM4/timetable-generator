"""Stage 5: 最小残余値ヒューリスティックによる決定的な貪欲配置。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
候補の少ない科目から順に確定させ、置けない科目は未配置として記録して
先へ進む。必ず有限時間で終わり、部分解を返す。
"""
from app.constraints.context import Context
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets

DEFAULT_NODE_LIMIT = 200_000


def _least_crowded(
    timetable: Timetable, options: list[tuple[TimeSlot, ...]]
) -> tuple[TimeSlot, ...]:
    """候補のうち、既に置かれている科目が最も少ないコマ集合を返す。

    候補は 月1→月2→…→金5 の順に並んでいるため、単純に先頭を採ると
    月曜から順に埋まり、木曜がほとんど使われない時間割になる。実データ
    では月 162・火 171 に対して木 6 という偏りが出た。偏りは見た目の
    問題にとどまらず、同じ曜日に科目が集中することで教員重複や必修衝突
    を生み、水・木が空いているのに置けない科目を作る。

    そこで最も空いているコマを選んで全体に散らす。候補が同数で並んだ
    場合は曜日・時限の順で決めるため、結果は決定的なままである。
    """
    return min(
        options,
        key=lambda slots: (
            sum(len(timetable.occupied_by(slot)) for slot in slots),
            tuple((slot.day, slot.period) for slot in slots),
        ),
    )

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
    置く場所は候補のうち最も空いているコマを選ぶ（_least_crowded 参照）。
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
        timetable.place(code, _least_crowded(timetable, options), AssignmentSource.SOLVER)

    unplaced.extend(remaining)
    return unplaced
