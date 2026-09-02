"""踏襲モード。

前年度の配置をそのまま使える科目はロックし、組み替えが必要な科目だけを
Stage 2〜5 に流す。事務局の確認負担を減らすことが目的。
"""
from dataclasses import dataclass, field
from pathlib import Path

from app.constraints.context import Context
from app.constraints.validator import is_allowed
from app.ingest.curriculum_reader import read_curriculum
from app.logging.session_logger import SessionLogger
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable

RETARGET_KINDS = (TeacherKind.PART_TIME, TeacherKind.SPECIAL)
"""非専任。出勤可能日が年度で変動するため常に組み替え対象。"""


@dataclass(frozen=True, slots=True)
class PreviousEntry:
    slots: tuple[TimeSlot, ...]
    teacher: str


@dataclass(slots=True)
class InheritPlan:
    previous_slots: dict[str, PreviousEntry] = field(default_factory=dict)
    retarget_codes: set[str] = field(default_factory=set)


def read_previous_timetable(path: str | Path) -> dict[str, PreviousEntry]:
    """前年度の時間割（カリキュラム一覧と同形式）を読む。

    曜日・時限が埋まっている科目だけを対象とする。集中講義は無視する。
    """
    entries: dict[str, PreviousEntry] = {}
    for subject in read_curriculum(path):
        if subject.is_intensive or subject.fixed_slot is None:
            continue
        entries[subject.code] = PreviousEntry(
            slots=tuple(subject.fixed_slot), teacher=subject.teacher
        )
    return entries


def detect_retarget_codes(
    subjects: list[Subject],
    teachers: dict[str, Teacher],
    previous_entries: dict[str, PreviousEntry],
    previous_teachers: dict[str, Teacher],
) -> set[str]:
    """組み替えが必要な科目コードを返す。"""
    retarget: set[str] = set()
    for subject in subjects:
        if subject.is_intensive:
            continue

        teacher = teachers.get(subject.teacher)
        if teacher is not None and teacher.kind in RETARGET_KINDS:
            retarget.add(subject.code)
            continue

        previous = previous_entries.get(subject.code)
        if previous is None:
            retarget.add(subject.code)
            continue

        if previous.teacher != subject.teacher:
            retarget.add(subject.code)
            continue

        before = previous_teachers.get(subject.teacher)
        after = teachers.get(subject.teacher)
        before_day = before.research_day if before else None
        after_day = after.research_day if after else None
        if before_day != after_day:
            retarget.add(subject.code)

    return retarget


def apply_plan(
    context: Context, timetable: Timetable, plan: InheritPlan, logger: SessionLogger
) -> None:
    """組み替え対象でない科目を前年度と同じコマに配置する。"""
    inherited = 0
    for code, previous in plan.previous_slots.items():
        if code in plan.retarget_codes:
            continue
        subject = context.subjects.get(code)
        if subject is None or timetable.is_placed(code):
            continue
        # 今年度は集中講義になった科目を、前年度の枠へ戻さない。集中は
        # グリッド対象外で別枠の一覧に出るため、載せると同じ科目が 2 か所に
        # 現れる。実データの J19901 模擬ブライダルプロジェクトがこれで、
        # 今年度は時限99 なのに前年度の 水5 へ置かれていた。
        if subject.is_intensive:
            continue
        if not is_allowed(context, timetable, subject, previous.slots):
            logger.warn(
                f"前年度の配置が今年度の制約に合いません: {subject.name}",
                stage="Stage 1",
            )
            continue
        timetable.place(code, previous.slots, AssignmentSource.INHERITED)
        inherited += 1

    logger.info(f"前年度から {inherited} 件を踏襲しました", stage="Stage 1")
    logger.info(f"組み替え対象は {len(plan.retarget_codes)} 件です", stage="Stage 1")
