"""教員に関する制約 H1・H5・H6・H7。

すべて「subject を slots に置いたら違反するか」を返す。timetable 上の
subject 自身の既存配置は無視する。
"""
from app.constraints.context import Context, Violation, others_at
from app.constraints.period_overlap import active_quarters
from app.ingest.department_rules import RULES
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

MAX_CONSECUTIVE = 3
"""同一教員が同一日に連続してよいコマ数の上限。

もとは 2 だった。ゼミの隣接（課題研究と卒業研究を隣り合う時限に置く）
を入れたところ、隣接させた時点でその教員はその曜日に 2 コマ連続する
ため、前後にもう 1 コマあると必ず H7 に触れて弾かれた。実データでは
隣接が成立したのは 63 組中 23 組にとどまり、未配置も 15 件に増えた。
3 に緩めると隣接 55 組・未配置 6 件になる。

1 人の教員にコマが積み上がる心配は要らない。時限は 1〜5 の 5 コマ
しかないので、1 日 5 コマ持つには全部を取るしかなく、それは 5 コマ
連続になってこの規則自体に触れる。**連続 3 コマまでという上限が、
1 日 4 コマまでという上限を自動的に含んでいる。**
"""

def check_h1(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同曜日・同時限に別科目を持たない（全学科横断）。

    合同ペアは 2 行に分かれていても物理的に 1 つの授業で、担当教員も
    同一である。H4 が同一コマへの配置を要求するため、joint_id が一致
    する相手は衝突とみなさない。除外しないと H1 と H4 が矛盾し、
    合同科目を一切配置できなくなる。
    """
    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if subject.joint_id and other.joint_id == subject.joint_id:
                continue
            if other.teacher and other.teacher == subject.teacher:
                violations.append(Violation(
                    rule_id="H1",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} が {slot} に "
                        f"{other.name} と重複しています"
                    ),
                    related_code=other.code,
                ))
    return violations


def check_h5(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """非常勤は出勤可能コマのみ、特任は出勤可能曜日のみ。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None:
        return []

    violations: list[Violation] = []
    if teacher.kind is TeacherKind.PART_TIME and teacher.available_slots:
        for slot in slots:
            if slot not in teacher.available_slots:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot} に出勤できません",
                ))
    if teacher.kind is TeacherKind.SPECIAL and teacher.available_days:
        for slot in slots:
            if slot.day not in teacher.available_days:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot.day}曜日に出勤できません",
                ))
    return violations


def check_h6(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """専任の研究日には配置しない。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None or not teacher.research_day:
        return []
    return [
        Violation(
            rule_id="H6",
            subject_code=subject.code,
            message=f"{teacher.name} の研究日（{teacher.research_day}曜日）です",
        )
        for slot in slots
        if slot.day == teacher.research_day
    ]


_LAST_LOAD: tuple | None = None
"""直前に計算した _teacher_day_load の結果を 1 件だけ覚えておく。

候補コマの列挙は 1 つの科目について何十通りものコマを試すが、この
走査結果はコマに依存しない。1 件覚えておくだけで同じ科目の 2 回目
以降がすべて再利用になり、実データでの生成時間が 80 秒から 59 秒に
縮んだ。

正しさは (timetable が同一オブジェクトか, その version, 教員名,
除外する科目コード) の一致で担保する。配置が変われば version が
増えるため、古い結果を使ってしまうことはない。
"""


def _teacher_day_load(
    context: Context, timetable: Timetable, subject: Subject
) -> dict[str, list[tuple[int, frozenset]]]:
    """担当教員の既存配置を「曜日 → (時限, 開講クオーター集合)」に集める。

    subject 自身の配置は除く。配置全体の走査は 1 回だけにしたい。
    曜日ごと・クオーター区間ごとに走査し直すと、実データ規模では
    生成時間が体感できるほど伸びる。
    """
    global _LAST_LOAD
    if _LAST_LOAD is not None:
        table, version, teacher, code, cached = _LAST_LOAD
        if (
            table is timetable
            and version == timetable.version
            and teacher == subject.teacher
            and code == subject.code
        ):
            return cached

    load: dict[str, list[tuple[int, frozenset]]] = {}
    if not subject.teacher:
        return load
    for code, assignment in timetable.assignments.items():
        if code == subject.code:
            continue
        other = context.subjects.get(code)
        if other is None or other.teacher != subject.teacher:
            continue
        windows = active_quarters(other.term, other.quarter)
        for slot in assignment.slots:
            # 事務局が編成を決めた枠は連続の数に入れない。会計学科 1 年の
            # 水曜は 1〜4 限が簿記で埋まると決まっており、担当教員はその
            # 4 コマが必ず連続する。同じ教員の他の授業は通常どおり数える。
            if RULES.exempt_from_consecutive_limit(other, slot):
                continue
            load.setdefault(slot.day, []).append((slot.period, windows))
    _LAST_LOAD = (timetable, timetable.version, subject.teacher, subject.code, load)
    return load


def _longest_run(periods: set[int]) -> int:
    longest = run = 0
    for period in sorted(periods):
        run = run + 1 if (period - 1) in periods else 1
        longest = max(longest, run)
    return longest


def check_h7(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同一日に 4 コマ以上連続しない。

    連続の判定はクオーター区間ごとに行う。H7 は 3 科目以上をまとめて
    見る唯一の制約であり、「subject と重なる科目」を一括りにすると、
    互いには重ならない後①と後②の科目まで一緒に数えてしまう。実データ
    では 水1（学期全体）・水2（後①）・水3（後②）という配置が 3 コマ
    連続と誤検出された。実際には後期前半が水1・水2、後期後半が水1・水3
    で、3 コマ連続する瞬間は存在しない。
    """
    violations: list[Violation] = []
    windows = active_quarters(subject.term, subject.quarter)
    load = _teacher_day_load(context, timetable, subject)

    for day in sorted({slot.day for slot in slots}):
        candidate = {
            slot.period for slot in slots
            if slot.day == day and not RULES.exempt_from_consecutive_limit(subject, slot)
        }
        existing = load.get(day, ())
        for window in sorted(windows, key=lambda q: q.value):
            occupied = {p for p, ws in existing if window in ws}
            occupied |= candidate
            if _longest_run(occupied) > MAX_CONSECUTIVE:
                violations.append(Violation(
                    rule_id="H7",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} の {day}曜日が "
                        f"{MAX_CONSECUTIVE + 1} コマ以上連続します"
                    ),
                ))
                break
    return violations


TEACHER_RULES = (check_h1, check_h5, check_h6, check_h7)
