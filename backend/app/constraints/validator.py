"""制約検証の唯一の入口。

Gemini の応答検証、ソルバーの枝刈り、フロントの D&D 編集判定は
すべてこのモジュールを経由する。ここを通らない検証を書いてはならない。

**ハード制約の一覧。** 破れない決まりで、これに触れる配置は作らない
（好み＝ソフト制約は scheduler/objectives.py にある）。ログや画面に出る
「[H2] …」の H2 はこの番号で、どのモジュールを見ればよいかもここで引ける。

    教員（teacher_rules.py）
      H1  同一教員が同曜日・同時限に別科目を持たない（全学科横断）
      H5  非常勤は出勤可能コマのみ、特任は出勤可能曜日のみ
      H6  専任の研究日には置かない
      H7  同一教員が同一日に 4 コマ以上連続しない

    学生（student_rules.py）
      H2  必修同士が衝突しない（学科 × 年次）
      H3  選択必修同士が衝突しない（学科 × 年次 × コース）

    科目（subject_rules.py）
      H4  合同科目のペアは同曜日・同時限
      H8  遠隔=○ は金曜のみ、遠隔=× は金曜以外（空欄はどちらでもよい）
      H9  Excel で入力済みの確定枠は動かせない
      H10 コマ数と連続要件を満たす（▲科目は連続 2 コマ）
      H12 前期・後期にまたがる対応科目は同曜日・同時限
      H13 朝学習の時間には授業を置かない

**H11 は欠番。** 「同一日に 5 コマ以上持たない」は不要である。時限は
1〜5 の 5 コマしかなく、5 コマ持つには全部取るほかないので、必ず 5 コマ
連続となって H7 が先に弾く。**番号は再利用しない**（ログに残る過去の
H11 が別の意味になってしまう）。

H2・H3 が「衝突しない」と言うとき、次の 2 つは衝突とみなさない。
どちらも学生が実際に受けるのは一方だけだからである。

    ・【再】が付いた再履修クラス（受けるのは 2 年生以降。Subject.is_retake）
    ・英語Ⅰ【A】〜【E】のようなクラス分け（Subject.class_group）
"""
from app.constraints.context import Context, Violation
from app.constraints.student_rules import STUDENT_RULES
from app.constraints.subject_rules import SUBJECT_RULES
from app.constraints.teacher_rules import TEACHER_RULES
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

ALL_RULES = TEACHER_RULES + STUDENT_RULES + SUBJECT_RULES


def check_placement(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """subject を slots に置いた場合の違反をすべて返す。

    timetable 上の subject 自身の既存配置は評価から除外される。
    """
    violations: list[Violation] = []
    for rule in ALL_RULES:
        violations.extend(rule(context, timetable, subject, slots))
    return violations


def is_allowed(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> bool:
    """1 件でも違反があれば False。ソルバーの枝刈りに使う。"""
    for rule in ALL_RULES:
        if rule(context, timetable, subject, slots):
            return False
    return True


def validate_all(context: Context, timetable: Timetable) -> list[Violation]:
    """完成した時間割を通しで検証する。違反は関係する両科目から報告される。"""
    violations: list[Violation] = []
    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        violations.extend(check_placement(context, timetable, subject, assignment.slots))
    return violations
