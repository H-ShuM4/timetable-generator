"""科目固有の制約 H4・H8・H9・H10・H12・H13。"""
from app.constraints.context import Context, Violation
from app.ingest.department_rules import RULES
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

FRIDAY = "金"


def _partners_elsewhere(context: Context, timetable: Timetable, subject: Subject,
                        slots: tuple[TimeSlot, ...], group: str,
                        rule_id: str, describe) -> list[Violation]:
    """同じまとまりの科目が、別のコマに置かれていないか調べる。

    H4（合同科目）と H12（前期・後期の対応科目）は、見るフィールドと
    文言が違うだけで判定は同じ。**同じ判定を 2 通り書くと、片方だけ
    直したときに気づけない。**

    `group` は突き合わせに使う属性名（"joint_id" か "pair_id"）、
    `describe` は相手の科目と置かれているコマから文言を作る関数。
    まだ置かれていない相手は見ない（置く順に依らないようにするため）。
    """
    mine = getattr(subject, group)
    candidate = set(slots)
    violations: list[Violation] = []
    for code, other in context.subjects.items():
        if code == subject.code or getattr(other, group) != mine:
            continue
        placed = timetable.slot_of(code)
        if not placed or set(placed) == candidate:
            continue
        violations.append(Violation(
            rule_id=rule_id,
            subject_code=subject.code,
            message=describe(other, placed),
            related_code=code,
        ))
    return violations


def _where(placed) -> str:
    return "・".join(str(s) for s in placed)


def check_h4(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """合同科目のペアは同曜日・同時限。"""
    if not subject.joint_id:
        return []
    return _partners_elsewhere(
        context, timetable, subject, slots, "joint_id", "H4",
        lambda other, placed:
            f"合同科目 {other.name} は {_where(placed)} に配置されています",
    )


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


def check_h12(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """前期・後期にまたがる対応科目は同曜日・同時限。

    日本語リテラシーⅠとⅡ、課題研究ⅠとⅡ、卒業研究ⅠとⅡのように、
    同じ教員が前期と後期に続けて受け持つ科目を指す。学生から見て
    通年で同じコマに出席できるようにするための運用規則である。

    H4 と形は同じだが対象が違う。H4 は同じ学期の経営・会計の合同科目、
    H12 は同じ学科の前期・後期の対応科目である。両方が付く科目もある
    （課題研究Ⅰは経営・会計で合同かつ、課題研究Ⅱと対応する）。

    対応関係は `config/paired_subjects.json` で定義する。
    """
    if not subject.pair_id:
        return []
    return _partners_elsewhere(
        context, timetable, subject, slots, "pair_id", "H12",
        lambda other, placed:
            f"対応科目 {other.name}（{other.term.value}）は "
            f"{_where(placed)} に配置されています",
    )


def morning_study_yields_to_availability(context: Context, subject: Subject) -> bool:
    """出勤可能コマがすべて朝学習に重なるか。

    非常勤の出勤可能コマ（H5）と朝学習（H13）がぶつかったときは、
    **出勤可能コマを優先する**。朝学習は時間帯の運用、出勤可能コマは
    その先生が来られるかどうかで、後者は動かしようがない。

    実例：リサーチ入門:会 の担当は金 1 限しか出勤できない非常勤で、
    その金 1 が朝学習になった。朝学習を通すとこの科目は置き場所を失う。

    列挙ではなく条件で書いているのは、事務局が教員一覧を更新するたびに
    同じ組み合わせが新しく生まれうるためである。
    """
    teacher = context.teachers.get(subject.teacher)
    if teacher is None or not teacher.available_slots:
        return False
    return all(
        RULES.morning_study_blocks(subject, slot) for slot in teacher.available_slots
    )


def check_h13(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """朝学習の時間には授業を置かない。

    会計学科 1 年は月・火・木・金の 1 限が朝学習にあてられている。
    水曜だけは朝学習が無く、1 限から 4 限まで事務局が編成を決めている。

    対象は `config/department_rules.json` に書く。他の学科・学年に
    同じ運用が現れたら、コードを触らずに足せる。

    担当教員の出勤可能コマがすべて朝学習に重なる場合は、この規則が譲る
    （`morning_study_yields_to_availability` 参照）。

    **【再】には掛からない。** 朝学習は 1 年生の運用で、再履修クラスを
    受けるのは 2 年生以降だからである。実データでは 会計1年【再】13 件が
    この規則で月火木金の 1 限から締め出されていた。
    """
    if subject.is_retake:
        return []
    if morning_study_yields_to_availability(context, subject):
        return []
    return [
        Violation(
            rule_id="H13",
            subject_code=subject.code,
            message=f"{slot} は朝学習の時間です",
        )
        for slot in slots
        if RULES.morning_study_blocks(subject, slot)
    ]


SUBJECT_RULES = (check_h4, check_h8, check_h9, check_h10, check_h12, check_h13)
