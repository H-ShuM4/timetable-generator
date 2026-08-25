"""時間割の「良さ」を数える。制約ではなく好みである。

事務局が生成画面のスライダーで重みを決める。重みが 0 の項目は数えない
ので、すべて 0 にすれば修復は何も動かさず、結果は従来と同じになる。

**項目同士は競合する。** 登校日数を詰めれば 1 日が長くなって空きコマが
増えやすく、空きコマを潰せば登校日数が増えやすい。どちらを取るかは
事務局が実際の時間割を見比べて決めることなので、system 側では
重み付き合計にして順位を付けるだけにしてある。
"""
import collections
from dataclasses import dataclass

from app.constraints.context import Context
from app.models.enums import Category, Department
from app.models.timetable import Timetable

PREFER_EARLY_DEPARTMENTS = (
    Department.MANAGEMENT,
    Department.ACCOUNTING,
    Department.JUNIOR,
)
LATE_PERIOD = 5

WEIGHT_STEPS = {"off": 0.0, "normal": 1.0, "high": 3.0}
"""スライダー 3 段階。気にしない／標準／重視。"""


@dataclass(frozen=True, slots=True)
class Weights:
    student_gaps: float = 1.0
    student_days: float = 0.0
    teacher_gaps: float = 0.0
    early_periods: float = 1.0
    seminar_adjacency: float = 1.0

    @classmethod
    def from_steps(cls, steps: dict) -> "Weights":
        """画面から届く {"student_gaps": "high", ...} を重みへ直す。"""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        values = {
            name: WEIGHT_STEPS[value]
            for name, value in (steps or {}).items()
            if name in known and value in WEIGHT_STEPS
        }
        return cls(**values)

    @property
    def is_idle(self) -> bool:
        """すべて 0 なら修復しても順位が付かない。"""
        return not any((
            self.student_gaps, self.student_days, self.teacher_gaps,
            self.early_periods, self.seminar_adjacency,
        ))


def _runs_gap(periods: set[int]) -> int:
    """最初と最後の間で授業が無いコマ数。"""
    return 0 if len(periods) < 2 else (max(periods) - min(periods) + 1) - len(periods)


@dataclass(slots=True)
class Snapshot:
    """時間割 1 つぶんの計測値。移動の前後で比べる。"""

    student_gaps: int = 0
    student_days: int = 0
    teacher_gaps: int = 0
    late_periods: int = 0
    seminars_apart: int = 0

    def score(self, weights: Weights) -> float:
        return (
            weights.student_gaps * self.student_gaps
            + weights.student_days * self.student_days
            + weights.teacher_gaps * self.teacher_gaps
            + weights.early_periods * self.late_periods
            + weights.seminar_adjacency * self.seminars_apart
        )


def measure(context: Context, timetable: Timetable) -> Snapshot:
    """時間割全体を 1 度走査して計測する。

    学生側は必修だけを見る。選択は履修者が分かれるので、空きコマや
    登校日数を全員ぶん語れない。必修は学科×年次の全員が出るため、
    そこだけが確実に言える。
    """
    cohorts: dict[tuple, dict[str, set[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    teachers: dict[tuple, dict[str, set[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    seminars: dict[str, list] = collections.defaultdict(list)
    late = 0

    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        for slot in assignment.slots:
            if subject.category is Category.REQUIRED:
                cohorts[(subject.department, subject.year, subject.term)][slot.day].add(slot.period)
            if subject.teacher:
                teachers[(subject.teacher, subject.term)][slot.day].add(slot.period)
            if (
                slot.period == LATE_PERIOD
                and subject.department in PREFER_EARLY_DEPARTMENTS
            ):
                late += 1
        if subject.adjacent_id:
            seminars[subject.adjacent_id].append(assignment.slots)

    apart = 0
    for slots_list in seminars.values():
        if len(slots_list) != 2:
            continue
        a, b = slots_list[0][0], slots_list[1][0]
        if a.day != b.day or abs(a.period - b.period) != 1:
            apart += 1

    return Snapshot(
        student_gaps=sum(_runs_gap(ps) for days in cohorts.values() for ps in days.values()),
        student_days=sum(len(days) for days in cohorts.values()),
        teacher_gaps=sum(_runs_gap(ps) for days in teachers.values() for ps in days.values()),
        late_periods=late,
        seminars_apart=apart,
    )
