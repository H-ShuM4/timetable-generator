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
    """同じ学生集団か。

    **【再】は配当年次の集団に属さない。** 1 年次に落単した学生が履修する
    再履修クラスなので、実際に受けるのは 2 年生以降になる。同じ年次の
    他の必修と被って構わない。ただし【再】同士は同じ集団として扱う。
    2 科目を同時に再履修する学生がいるため、重ねると片方を落とすことになる。
    """
    return (
        a.department is b.department
        and a.year == b.year
        and a.is_retake == b.is_retake
    )


def _same_subject(a: Subject, b: Subject) -> bool:
    """同じ科目の別クラスか。

    英語Ⅰ【A】と英語Ⅰ【B】は 1 科目を教員ごとに割ったもので、学生が
    履修するのはそのうち一つ。同一コマに集約してよい。担当教員が同じ
    場合は H1 が別に弾くので、ここでは見なくてよい。
    """
    return a.class_group == b.class_group


def check_h2(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """必修同士が衝突しない（学科 × 年次）。同一科目の複数クラスは除外。

    担当教員ごとにクラスが分かれていても、学生が履修するのはそのうち
    一つなので同一コマに集約してよい。ゼミ科目に限らず、英語Ⅰや
    商業簿記Ⅰ のような複数クラス開講の通常科目も同じ扱いになる。
    クラス記号（英語Ⅰ【A】の【A】）の違いもここで吸収する。

    【再】は配当年次の集団に属さないため、その年次の必修とは衝突しない
    （`_same_cohort` 参照）。
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
            if _same_subject(subject, other):
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

    同一科目の複数クラスを除外する点は H2 と同じ。実データに該当は
    無いが、必修だけ除外して選択必修は除外しない理由が無い。
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
            if _same_subject(subject, other):
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
