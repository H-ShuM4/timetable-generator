"""Stage 5: 決定的なバックトラッキング探索。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
探索が発散しないよう node_limit で必ず打ち切り、部分解を返す。
"""
from app.constraints.context import Context
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets

DEFAULT_NODE_LIMIT = 200_000


def solve(
    context: Context,
    timetable: Timetable,
    codes: list[str],
    *,
    node_limit: int = DEFAULT_NODE_LIMIT,
) -> list[str]:
    """codes を timetable に配置し、置けなかったコードを返す。

    既存の配置は動かさない。探索が node_limit に達した場合は、
    そこまでに置けた分を残して打ち切る。
    """
    targets = [
        code for code in codes
        if code in context.subjects
        and not context.subjects[code].is_intensive
        and not timetable.is_placed(code)
    ]
    if not targets:
        return []

    nodes = 0
    best_placed: dict[str, tuple] = {}

    def snapshot() -> dict[str, tuple]:
        return {code: timetable.slot_of(code) for code in targets if timetable.is_placed(code)}

    def search(remaining: list[str]) -> bool:
        nonlocal nodes, best_placed

        if not remaining:
            best_placed = snapshot()
            return True
        if nodes >= node_limit:
            return False

        options_by_code = {
            code: feasible_slot_sets(context, timetable, context.subjects[code])
            for code in remaining
        }
        if len(snapshot()) > len(best_placed):
            best_placed = snapshot()

        code = min(remaining, key=lambda c: len(options_by_code[c]))
        options = options_by_code[code]
        if not options:
            return False

        rest = [c for c in remaining if c != code]
        for slots in options:
            nodes += 1
            if nodes > node_limit:
                return False
            timetable.place(code, slots, AssignmentSource.SOLVER)
            if search(rest):
                return True
            timetable.remove(code)
        return False

    if search(targets):
        return []

    # 全体解が見つからなかった場合は、最も多く置けた部分解を復元する
    for code in targets:
        if timetable.is_placed(code):
            timetable.remove(code)
    for code, slots in best_placed.items():
        timetable.place(code, slots, AssignmentSource.SOLVER)

    return [code for code in targets if not timetable.is_placed(code)]
