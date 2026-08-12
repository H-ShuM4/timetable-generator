"""踏襲モード。Task 16 で本実装する。"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class InheritPlan:
    previous_slots: dict[str, tuple] = field(default_factory=dict)
    retarget_codes: set[str] = field(default_factory=set)


def apply_plan(context, timetable, plan, logger) -> None:
    raise NotImplementedError
