"""生成結果の取得と、ドラッグ&ドロップによる手動編集。

編集の可否判定は constraints.validator を通す。AI 経由と手動編集で
判定がずれないことがこの設計の要点。
"""
from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    MoveIn,
    MoveOut,
    PlacementOut,
    ResultOut,
    SlotState,
    SubjectRef,
    TeacherOut,
    UnplaceIn,
    ViolationOut,
)
from app.constraints.linking import linked_group
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


def _to_teacher_refs(context) -> list[TeacherOut]:
    """教員ビューで担当コマ数と勤務条件を突き合わせるために返す。"""
    return [
        TeacherOut(
            name=teacher.name,
            kind=teacher.kind.value,
            research_day=teacher.research_day,
            available_slots=sorted(f"{s.day}{s.period}" for s in teacher.available_slots),
        )
        for teacher in sorted(context.teachers.values(), key=lambda t: t.name)
    ]


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
            slots_required=subject.slots_required,
            requires_consecutive=subject.requires_consecutive,
        ))
    return refs


@router.post("/{session_id}/unplace", response_model=MoveOut)
async def unplace(session_id: str, payload: UnplaceIn) -> MoveOut:
    """科目を時間割から外し、未配置一覧へ戻す。

    未配置科目を手で置いた操作を取り消すために要る。外すだけなので
    制約に触れることはなく、必ず成功する。
    """
    data = _require_session(session_id)
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    context = data.context
    if payload.code not in context.subjects:
        raise HTTPException(status_code=404, detail="科目が見つかりません")

    timetable = data.result.timetable
    previous = [
        SlotState(code=payload.code, slots=[str(s) for s in timetable.slot_of(payload.code)])
    ]
    timetable.remove(payload.code)
    if payload.code not in data.result.unplaced:
        data.result.unplaced.append(payload.code)

    data.result.violations = validate_all(context, timetable)
    store.save_result(session_id)
    return MoveOut(applied=True, violations=[], previous=previous)


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
        teachers=_to_teacher_refs(context),
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
    group = linked_group(context, subject)
    # 取り消しのために、動かす前の状態をグループ全員ぶん控える。
    # 未配置だった科目は空のリストで表す。
    previous = [
        SlotState(code=code, slots=[str(s) for s in timetable.slot_of(code)])
        for code in group
    ]

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

    # 置いたものは未配置ではない。ここを忘れると一覧と時間割が食い違う。
    data.result.unplaced = [
        code for code in data.result.unplaced if not timetable.is_placed(code)
    ]
    data.result.violations = validate_all(context, timetable)
    store.save_result(session_id)

    return MoveOut(applied=True, violations=[], previous=previous)
