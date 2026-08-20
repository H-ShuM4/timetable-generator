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


def _joint_group(context, subject) -> list[str]:
    """subject と一緒に動かすべき科目コードの一覧。

    合同科目は経営側と会計側の 2 行に分かれているが物理的には 1 つの
    授業なので、片方を動かせばもう片方も同じコマへ動く。合同でなければ
    その科目だけを返す。
    """
    if not subject.joint_id:
        return [subject.code]
    return sorted(
        code for code, other in context.subjects.items()
        if other.joint_id == subject.joint_id
    )


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
    group = _joint_group(context, subject)

    # グループを一度すべて外してから検証する。合同ペアは H4 が同一コマを
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
