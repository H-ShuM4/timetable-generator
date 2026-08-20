"""Stage 5: 最小残余値ヒューリスティックによる決定的な貪欲配置。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
候補の少ない科目から順に確定させ、置けない科目は未配置として記録して
先へ進む。必ず有限時間で終わり、部分解を返す。
"""
from app.constraints.context import Context
from app.models.enums import Department
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets

DEFAULT_NODE_LIMIT = 200_000


LATE_PERIOD = 5
"""できれば避けたい時限。"""

PREFER_EARLY_PERIODS = (
    Department.MANAGEMENT,
    Department.ACCOUNTING,
    Department.JUNIOR,
)
"""1〜4 限への集約を優先する学科。

もともとの要望は大学（経営・会計）についてであった。大学には通常の
カリキュラムに加えて教職課程の科目があり、それらは 4 限・5 限に置かれる
ことが多いため、通常科目を 1〜4 限に寄せておくと競合しにくい。

短期大学部も対象に含めているのは、大学だけを対象にすると大学が空けた
5 限へ短大が押し出されるためである。実データでは短大の 5 限が 15.8% から
45.2% に跳ね上がった。全学科を対象にすると 経営 0.8%・会計 0.9%・
短大 3.4% となり、未配置数も変わらない。短大を除外したい場合はこの
タプルから外すだけでよい。
"""


def _placement_preference(
    timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> tuple:
    """候補コマ集合の望ましさ。小さいほど望ましい。

    これは制約ではなく好みである。5 限しか空いていなければ 5 限に置く。
    配置可能なものを拒否することは一切しない。

    順に、(1) 避けたい時限を使う数、(2) 既に置かれている科目の数、
    (3) 曜日・時限。(3) は同点時の決定性のためだけにある。

    (2) が要る理由：候補は 月1→月2→…→金5 の順に並んでいるため単純に
    先頭を採ると月曜から順に埋まる。実データでは月 162・火 171 に対して
    木 6 という偏りが出た。偏りは見た目だけの問題ではなく、同じ曜日に
    科目が集中することで教員重複や必修衝突を生み、水・木が空いているのに
    置けない科目を作る。
    """
    late = 0
    if subject.department in PREFER_EARLY_PERIODS:
        late = sum(1 for slot in slots if slot.period == LATE_PERIOD)
    return (
        late,
        sum(len(timetable.occupied_by(slot)) for slot in slots),
        tuple((slot.day, slot.period) for slot in slots),
    )


def _best_option(
    timetable: Timetable, subject: Subject, options: list[tuple[TimeSlot, ...]]
) -> tuple[TimeSlot, ...]:
    """候補のうち最も望ましいコマ集合を返す。"""
    return min(options, key=lambda slots: _placement_preference(timetable, subject, slots))

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
    置く場所は候補のうち最も望ましいコマを選ぶ（_placement_preference 参照）。
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
            code, _best_option(timetable, context.subjects[code], options),
            AssignmentSource.SOLVER,
        )

    unplaced.extend(remaining)
    return unplaced
