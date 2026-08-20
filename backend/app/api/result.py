"""生成結果の取得と、ドラッグ&ドロップによる手動編集。

編集の可否判定は constraints.validator を通す。AI 経由と手動編集で
判定がずれないことがこの設計の要点。
"""
from fastapi import APIRouter, HTTPException

from app.api.schemas import MoveIn, MoveOut, PlacementOut, ResultOut, SubjectRef, ViolationOut
from app.constraints.validator import check_placement, validate_all
from app.gemini.prompts import parse_slot_label, slot_label
from app.models.timetable import AssignmentSource
from app.session_store import store

router = APIRouter(prefix="/api/result", tags=["result"])


def _require_session(session_id: str):
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return data


def _to_violation(violation) -> ViolationOut:
    return ViolationOut(
        rule_id=violation.rule_id,
        subject_code=violation.subject_code,
        message=violation.message,
        related_code=violation.related_code,
    )


def _to_subject_refs(codes: list[str], context) -> list[SubjectRef]:
    refs: list[SubjectRef] = []
    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        refs.append(SubjectRef(
            code=subject.code,
            name=subject.name,
            teacher=subject.teacher,
            department=subject.department.value,
            year=subject.year,
            term=subject.term.value,
            category=subject.category.value,
        ))
    return refs


def _linked_group(context, subject) -> list[str]:
    """subject と同じコマに置かれるべき科目コードの一覧。

    2 種類の結び付きがあり、どちらも「同じ曜日・時限」を要求する。

    - `joint_id`（H4）：経営側と会計側に分かれた 1 つの合同授業
    - `pair_id`（H12）：同じ教員が前期と後期に続けて持つ対応科目

    両方を持つ科目があるため、**推移的に**たどる必要がある。課題研究Ⅰ
    の経営側を動かすと、合同相手の会計側と、後期の課題研究Ⅱの経営側・
    会計側まで、4 科目が一緒に動く。片方だけ動かすと H4 か H12 に必ず
    引っかかるので、まとめて動かす以外に選択肢はない。
    """
    by_key: dict[tuple[str, str], list[str]] = {}
    for code, other in context.subjects.items():
        for attribute in ("joint_id", "pair_id"):
            value = getattr(other, attribute)
            if value:
                by_key.setdefault((attribute, value), []).append(code)

    group = {subject.code}
    queue = [subject.code]
    while queue:
        current = context.subjects[queue.pop()]
        for attribute in ("joint_id", "pair_id"):
            value = getattr(current, attribute)
            if not value:
                continue
            for code in by_key.get((attribute, value), ()):
                if code not in group:
                    group.add(code)
                    queue.append(code)
    return sorted(group)


@router.get("/{session_id}", response_model=ResultOut)
async def get_result(session_id: str) -> ResultOut:
    data = _require_session(session_id)
    if data.result is None:
        status = "failed" if data.error else ("running" if data.running else "pending")
        return ResultOut(
            status=status,
            placements=[], unplaced=[], violations=[], intensive=[],
            error=data.error,
        )

    context = data.context
    placements = []
    for code, assignment in data.result.timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        placements.append(PlacementOut(
            code=code,
            name=subject.name,
            teacher=subject.teacher,
            department=subject.department.value,
            year=subject.year,
            term=subject.term.value,
            quarter=subject.quarter.value if subject.quarter else None,
            category=subject.category.value,
            slots=[slot_label(s) for s in assignment.slots],
            source=assignment.source.value,
        ))

    return ResultOut(
        status="done",
        placements=placements,
        unplaced=_to_subject_refs(data.result.unplaced, context),
        violations=[_to_violation(v) for v in data.result.violations],
        intensive=_to_subject_refs(data.result.intensive_codes, context),
    )


@router.post("/{session_id}/move", response_model=MoveOut)
async def move(session_id: str, payload: MoveIn) -> MoveOut:
    data = _require_session(session_id)
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    context = data.context
    subject = context.subjects.get(payload.code)
    if subject is None:
        raise HTTPException(status_code=404, detail="科目が見つかりません")

    try:
        slots = tuple(parse_slot_label(label) for label in payload.slots)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    timetable = data.result.timetable
    group = _linked_group(context, subject)

    # グループを一度すべて外してから検証する。H4 と H12 が同一コマを
    # 要求するため、片方を置いたまま相手を動かそうとすると必ず弾かれる。
    original = {
        code: (timetable.slot_of(code), timetable.assignments[code].source)
        for code in group
        if timetable.is_placed(code)
    }
    for code in original:
        timetable.remove(code)

    violations = []
    for code in group:
        violations.extend(check_placement(context, timetable, context.subjects[code], slots))

    if not violations:
        for code in group:
            timetable.place(code, slots, AssignmentSource.MANUAL)
        # 置いた結果で全体を検証し直す。グループ内で新たな違反が出た場合は
        # 移動そのものを取り消す。
        recheck = validate_all(context, timetable)
        introduced = [v for v in recheck if v.subject_code in group]
        if introduced:
            violations = introduced
            for code in group:
                timetable.remove(code)

    if violations:
        for code, (slots_before, source) in original.items():
            timetable.place(code, slots_before, source)
        return MoveOut(applied=False, violations=[_to_violation(v) for v in violations])

    data.result.violations = validate_all(context, timetable)
    store.save_result(session_id)

    return MoveOut(applied=True, violations=[])
