"""経営学科と会計学科で合同開講される科目を対応付ける。

合同=○ は科目が合同開講であることを示すフラグで、実際の対応付けは
教員単位で成立する。片方の学科にしかコマがない教員は単独のままが正常。

一方、同じ鍵の科目が他学科にあるのに片方だけフラグが付いている場合は
付け忘れの可能性が高いので、その科目コードを返して警告に回す。
"""
from collections import defaultdict

from app.models.enums import Department
from app.models.subject import Subject

JOINT_DEPARTMENTS = (Department.MANAGEMENT, Department.ACCOUNTING)
"""合同開講の対象学科。合同(経・会) 列は大学シートにしか存在しない。"""


def assign_joint_ids(subjects: list[Subject]) -> list[str]:
    """合同科目に joint_id を付与し、フラグ付け忘れの科目コードを返す。

    subjects の joint_id を破壊的に書き換える。
    """
    groups: dict[tuple[str, str, str], list[Subject]] = defaultdict(list)
    for subject in subjects:
        if subject.department not in JOINT_DEPARTMENTS:
            continue
        key = (subject.base_name, subject.teacher, subject.term.value)
        groups[key].append(subject)

    mismatches: list[str] = []
    for index, key in enumerate(sorted(groups), start=1):
        members = groups[key]
        flagged_departments = {m.department for m in members if m.is_joint}
        if not flagged_departments:
            continue

        if len(flagged_departments) >= 2:
            joint_id = f"J{index:03d}"
            for member in members:
                if member.is_joint:
                    member.joint_id = joint_id

        # フラグの付いたクラスが 1 つも無い学科だけが付け忘れの疑い。
        # 同一学科に複数クラスあり片方だけ合同、という構造は正常。
        mismatches.extend(
            member.code for member in members
            if member.department not in flagged_departments
        )

    return sorted(mismatches)
