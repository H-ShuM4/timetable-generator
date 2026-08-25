"""Stage 0 の警告を生成する。

警告があっても生成は止めない。フロントに一覧を出し、事務局が
Excel を直すか、そのまま進めるかを判断する。
"""
from dataclasses import dataclass

from app.ingest.department_rules import RULES
from app.models.enums import Category, TeacherKind
from app.models.subject import Subject
from app.models.teacher import Teacher


@dataclass(frozen=True, slots=True)
class Warning:
    kind: str
    message: str
    subject_code: str | None = None
    teacher_name: str | None = None


def collect_warnings(
    subjects: list[Subject],
    teachers: dict[str, Teacher],
    joint_flag_mismatch_codes: list[str],
) -> list[Warning]:
    warnings: list[Warning] = []
    seen_unknown: set[str] = set()
    seen_missing_availability: set[str] = set()
    mismatches = set(joint_flag_mismatch_codes)

    for subject in subjects:
        teacher = teachers.get(subject.teacher)

        # 朝学習の時間に授業が入ることになる科目は、黙って通さず知らせる。
        # 制約としては正しく譲っているが、事務局にとっては例外扱いである。
        if (
            teacher is not None
            and teacher.available_slots
            and all(RULES.morning_study_blocks(subject, slot)
                    for slot in teacher.available_slots)
        ):
            warnings.append(Warning(
                kind="morning_study_exception",
                message=(
                    f"出勤可能コマが朝学習と重なるため、朝学習の時間に配置します: "
                    f"{subject.name}（{subject.teacher}）"
                ),
                subject_code=subject.code,
                teacher_name=subject.teacher,
            ))

        if teacher is None:
            if subject.teacher not in seen_unknown:
                seen_unknown.add(subject.teacher)
                warnings.append(Warning(
                    kind="unknown_teacher",
                    message=f"教員一覧に存在しない担当教員です: {subject.teacher}",
                    teacher_name=subject.teacher,
                ))
        elif (
            teacher.kind is TeacherKind.PART_TIME
            and not teacher.available_slots
            and teacher.name not in seen_missing_availability
        ):
            seen_missing_availability.add(teacher.name)
            warnings.append(Warning(
                kind="missing_availability",
                message=f"担当科目がありますが出勤可能日が空欄です: {teacher.name}",
                teacher_name=teacher.name,
            ))

        if subject.code in mismatches:
            warnings.append(Warning(
                kind="joint_flag_mismatch",
                message=(
                    f"他学科に同じ科目・教員・開講期の科目がありますが、"
                    f"合同フラグが付いていません: {subject.name}"
                ),
                subject_code=subject.code,
            ))

        if subject.category is Category.ELECTIVE_REQUIRED and not subject.courses:
            warnings.append(Warning(
                kind="missing_course",
                message=f"選択必修ですがコースが未設定です: {subject.name}",
                subject_code=subject.code,
            ))

    return warnings


def check_partial_slots(rows: list[dict]) -> list[Warning]:
    """曜日と時限の片方だけが入力されている行を検出する。

    Subject に変換すると片側だけの情報は失われるため、Excel の行を
    そのまま受け取って判定する。
    """
    warnings: list[Warning] = []
    for row in rows:
        day = row.get("曜日")
        period = row.get("時限")
        if bool(day) != (period not in (None, "")):
            warnings.append(Warning(
                kind="partial_slot",
                message=f"曜日と時限の片方だけが入力されています: {row.get('授業コード')}",
                subject_code=row.get("授業コード"),
            ))
    return warnings
