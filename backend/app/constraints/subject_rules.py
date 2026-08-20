"""科目固有の制約 H4・H8・H9・H10。"""
from app.constraints.context import Context, Violation
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

FRIDAY = "金"


def check_h4(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """合同科目のペアは同曜日・同時限。"""
    if not subject.joint_id:
        return []

    candidate = set(slots)
    violations: list[Violation] = []
    for code, other in context.subjects.items():
        if code == subject.code or other.joint_id != subject.joint_id:
            continue
        placed = timetable.slot_of(code)
        if not placed:
            continue
        if set(placed) != candidate:
            violations.append(Violation(
                rule_id="H4",
                subject_code=subject.code,
                message=(
                    f"合同科目 {other.name} は "
                    f"{'・'.join(str(s) for s in placed)} に配置されています"
                ),
                related_code=code,
            ))
    return violations


def check_h8(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """遠隔=○ は金曜のみ、遠隔=× は金曜以外。空欄はどちらでもよい。

    大学（経営・会計）の金曜は全科目が遠隔授業である。したがって遠隔で
    行うと決めた科目（○）は金曜に置き、遠隔で行えない科目（×）は金曜に
    置けない。大学シートは全行が ○ か × のいずれかで、この 2 つで
    金曜の可否が決まる。

    短期大学部の金曜は遠隔と対面が混在する。○ は同じく金曜必須だが、
    残りは空欄で、他のハード制約を満たすなら金曜に置いてよい。

    空欄を × と同じ扱いにしてはいけない。短大の 153 科目が空欄であり、
    それらを金曜から締め出すと配置可能性が大きく下がる。
    """
    if subject.is_remote:
        return [
            Violation(
                rule_id="H8",
                subject_code=subject.code,
                message=f"遠隔科目のため金曜に配置してください（候補: {slot}）",
            )
            for slot in slots
            if slot.day != FRIDAY
        ]

    if subject.is_remote_prohibited:
        return [
            Violation(
                rule_id="H8",
                subject_code=subject.code,
                message=f"遠隔不可の科目は金曜に配置できません（候補: {slot}）",
            )
            for slot in slots
            if slot.day == FRIDAY
        ]
    return []


def check_h9(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """Excel で入力済みの確定枠は動かせない。"""
    if subject.fixed_slot is None:
        return []
    if set(slots) == set(subject.fixed_slot):
        return []
    fixed = "・".join(str(s) for s in subject.fixed_slot)
    return [Violation(
        rule_id="H9",
        subject_code=subject.code,
        message=f"確定枠（{fixed}）から動かすことはできません",
    )]


def check_h10(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """コマ数と連続要件を満たすこと。"""
    if len(slots) != subject.slots_required:
        return [Violation(
            rule_id="H10",
            subject_code=subject.code,
            message=f"必要コマ数は {subject.slots_required} ですが {len(slots)} が指定されました",
        )]

    if len(set(slots)) != len(slots):
        return [Violation(
            rule_id="H10",
            subject_code=subject.code,
            message="同じコマが重複して指定されました",
        )]

    if not subject.requires_consecutive:
        return []

    days = {slot.day for slot in slots}
    periods = sorted(slot.period for slot in slots)
    is_consecutive = len(days) == 1 and all(
        periods[i] + 1 == periods[i + 1] for i in range(len(periods) - 1)
    )
    if is_consecutive:
        return []
    return [Violation(
        rule_id="H10",
        subject_code=subject.code,
        message="▲科目のため同一曜日の連続コマに配置してください",
    )]


SUBJECT_RULES = (check_h4, check_h8, check_h9, check_h10)
