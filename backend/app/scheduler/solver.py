"""Stage 5: 最小残余値ヒューリスティックによる決定的な貪欲配置。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
候補の少ない科目から順に確定させ、置けない科目は未配置として記録して
先へ進む。必ず有限時間で終わり、部分解を返す。
"""
from app.constraints.context import Context
from app.constraints.linking import linked_group
from app.constraints.validator import check_placement
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets
from app.scheduler.preference import best_option

DEFAULT_NODE_LIMIT = 200_000


def _adjacent_partner_placed(context: Context, timetable: Timetable, code: str) -> bool:
    """隣接させたい相手が既に配置済みか。"""
    subject = context.subjects[code]
    if not subject.adjacent_id:
        return False
    return any(
        other.adjacent_id == subject.adjacent_id
        and other_code != code
        and timetable.is_placed(other_code)
        for other_code, other in context.subjects.items()
    )


def _pending_partners(context: Context, code: str, pending: set[str]) -> list[str]:
    """code と同じコマに入るべきで、まだ処理待ちの科目。

    候補が 1 つも無く未配置として記録済みの科目は pending に無いので
    対象にならない。一度未配置と決めたものを後から置くと、未配置一覧と
    時間割が食い違う。
    """
    return [
        other for other in linked_group(context, context.subjects[code])
        if other != code and other in pending
    ]


def _options_for_the_whole_group(
    context: Context,
    timetable: Timetable,
    options: list[tuple[TimeSlot, ...]],
    partners: list[str],
) -> list[tuple[TimeSlot, ...]]:
    """相手も一緒に置ける候補だけに絞る。

    H4 と H12 は「置いたあと」にしか効かない。前期の科目を先に置いて
    しまうと、後期の相手はそのコマしか選べなくなり、そこが後期の別の
    必修で埋まっていれば詰む。実データではこれで日本語リテラシーの
    4 科目が置けなくなっていた（前期の相手が月1 に入り、後期の月1 は
    情報処理Ⅰ【A】が占めていた）。

    相手は別の学期なので、こちらを置いても相手の判定は変わらない。
    H1・H2・H3 はいずれも開講期間が重なる科目しか見ないためである。
    したがって現在の時間割のまま相手を検査してよい。
    """
    return [
        slots for slots in options
        if all(
            not check_placement(context, timetable, context.subjects[partner], slots)
            for partner in partners
        )
    ]


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
        # 候補数が同じ場合は、隣接させたい相手が既に置かれている科目を
        # 先に確定させる。間に他の科目が入って隣のコマが埋まる前に置けば
        # 隣接が成立しやすい。最後は授業コード順にして結果を決定的にする。
        code = min(
            remaining,
            key=lambda c: (
                len(options_by_code[c]),
                0 if _adjacent_partner_placed(context, timetable, c) else 1,
                c,
            ),
        )
        remaining.remove(code)

        options = options_by_code[code]
        if not options:
            unplaced.append(code)
            continue

        # 同じコマに入るべき相手がまだ置かれていなければ、相手も置ける
        # 候補だけに絞る。相手ごと詰むコマを先に潰しておく。
        partners = _pending_partners(context, code, set(remaining))
        if partners:
            shared = _options_for_the_whole_group(context, timetable, options, partners)
            # 全員が入れるコマが 1 つも無い場合は、この科目だけでも置く。
            # 相手は置けなくなるが、誰も置かないより配置数は多くなる。
            options = shared or options

        chosen = best_option(timetable, context.subjects[code], options, context)
        timetable.place(code, chosen, AssignmentSource.SOLVER)
        # 相手も同じコマへ確定させる。ここで置かないと、次の反復までに
        # 別の科目がそのコマを埋めてしまう可能性がある。
        for partner in partners:
            if not check_placement(context, timetable, context.subjects[partner], chosen):
                timetable.place(partner, chosen, AssignmentSource.SOLVER)
                remaining.remove(partner)

    unplaced.extend(remaining)
    return unplaced
