"""学生の履修衝突に関する制約 H2・H3。

選択科目（Category.ELECTIVE）には学生側の衝突制約をかけない。
これは仕様上の決定であり、実装漏れではない。
"""
from app.constraints.context import Context, Violation, others_at
from app.models.enums import Category
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


def _same_cohort(a: Subject, b: Subject) -> bool:
    return a.department is b.department and a.year == b.year


def check_h2(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """必修同士が衝突しない（学科 × 年次）。同一科目の複数クラスは除外。

    担当教員ごとにクラスが分かれていても、学生が履修するのはそのうち
    一つなので同一コマに集約してよい。ゼミ科目に限らず、英語Ⅰや
    商業簿記Ⅰ のような複数クラス開講の通常科目も同じ扱いになる。
    """
    if subject.category is not Category.REQUIRED:
        return []

    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if other.category is not Category.REQUIRED:
                continue
            if not _same_cohort(subject, other):
                continue
            if subject.base_name == other.base_name:
                continue
            violations.append(Violation(
                rule_id="H2",
                subject_code=subject.code,
                message=(
                    f"{subject.department.value}{subject.year}年の必修同士が "
                    f"{slot} で重複しています（{other.name}）"
                ),
                related_code=other.code,
            ))
    return violations


def check_h3(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """選択必修同士が衝突しない（学科 × 年次 × コース）。

    どちらかのコースが未設定の場合は判定不能として違反にしない。
    Stage 0 で missing_course 警告を出しているため見落としにはならない。
    """
    if subject.category is not Category.ELECTIVE_REQUIRED or not subject.courses:
        return []

    own_courses = set(subject.courses)
    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if other.category is not Category.ELECTIVE_REQUIRED or not other.courses:
                continue
            if not _same_cohort(subject, other):
                continue
            shared = own_courses & set(other.courses)
            if not shared:
                continue
            violations.append(Violation(
                rule_id="H3",
                subject_code=subject.code,
                message=(
                    f"{'・'.join(sorted(shared))} の選択必修同士が "
                    f"{slot} で重複しています（{other.name}）"
                ),
                related_code=other.code,
            ))
    return violations


STUDENT_RULES = (check_h2, check_h3)
