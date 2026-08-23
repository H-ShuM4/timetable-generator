"""Stage 0〜6 のオーケストレーション。

Gemini 段階は gemini_placer として注入する。注入しなければ
モックモードと同じ経路になるため、テストに API キーは要らない。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.constraints.context import Context, Violation
from app.constraints.validator import validate_all
from app.ingest.pair_linking import link_subjects
from app.ingest.validators import Warning, collect_warnings
from app.logging.session_logger import SessionLogger
from app.models.enums import Category
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timetable import Timetable
from app.scheduler.inherit import InheritPlan, apply_plan
from app.scheduler.prelock import prelock
from app.scheduler.solver import solve

STAGE_ORDER: tuple[tuple[str, Category], ...] = (
    ("Stage 2", Category.REQUIRED),
    ("Stage 3", Category.ELECTIVE_REQUIRED),
    ("Stage 4", Category.ELECTIVE),
)


class GenerationMode(str, Enum):
    MOCK = "mock"
    OPTIMIZE = "optimize"
    INHERIT = "inherit"

    @property
    def label(self) -> str:
        """画面に出している呼び名。ログもこれで書く。

        識別子は API と設定を跨いで使うので変えない。事務局が読むのは
        画面とログなので、その 2 つの呼び名だけを揃える。
        """
        return {
            "mock": "モックモード",
            "optimize": "AI モード",
            "inherit": "踏襲モード",
        }[self.value]


class GeminiPlacer(Protocol):
    def __call__(
        self,
        context: Context,
        timetable: Timetable,
        codes: list[str],
        logger: SessionLogger,
    ) -> list[str]:
        """配置できなかった科目コードを返す。"""


@dataclass(slots=True)
class GenerationResult:
    timetable: Timetable
    unplaced: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    intensive_codes: list[str] = field(default_factory=list)


def run_pipeline(
    subjects: list[Subject],
    teachers: list[Teacher] | dict[str, Teacher],
    mode: GenerationMode,
    logger: SessionLogger,
    *,
    gemini_placer: GeminiPlacer | None = None,
    inherit_plan: "InheritPlan | None" = None,
) -> GenerationResult:
    logger.info(f"生成を開始します（{mode.label}）", stage="Stage 0")

    joint_mismatches = link_subjects(subjects)
    context = Context.from_lists(subjects, teachers)
    warnings = collect_warnings(subjects, context.teachers, joint_mismatches)
    for warning in warnings:
        logger.warn(warning.message, stage="Stage 0")
    logger.info(
        f"科目 {len(subjects)} 件、教員 {len(context.teachers)} 名を読み込みました",
        stage="Stage 0",
    )

    intensive_codes = [s.code for s in subjects if s.is_intensive]
    if intensive_codes:
        logger.info(
            f"集中講義 {len(intensive_codes)} 件をグリッド対象外にしました", stage="Stage 0"
        )

    timetable, leftover = prelock(context, subjects)
    logger.info(f"事前ロック {len(timetable.placed_codes())} 件", stage="Stage 1")
    for code in leftover:
        logger.warn(f"非常勤の出勤可能コマに空きがありません: {code}", stage="Stage 1")

    if mode is GenerationMode.INHERIT and inherit_plan is not None:
        apply_inherit_plan(context, timetable, inherit_plan, logger)

    pending = [
        s.code for s in subjects
        if not s.is_intensive and not timetable.is_placed(s.code)
    ]

    if mode is not GenerationMode.MOCK and gemini_placer is not None:
        for stage_name, category in STAGE_ORDER:
            codes = [c for c in pending if context.subjects[c].category is category]
            if not codes:
                continue
            logger.info(f"{category.value} {len(codes)} 件を配置します", stage=stage_name)
            failed = gemini_placer(context, timetable, codes, logger)
            placed = len(codes) - len(failed)
            logger.info(f"{placed} 件を配置、{len(failed)} 件が未確定", stage=stage_name)
            pending = [c for c in pending if not timetable.is_placed(c)]

    if pending:
        logger.info(f"ソルバーで {len(pending)} 件を補完します", stage="Stage 5")
    unplaced = solve(context, timetable, pending)
    for code in unplaced:
        logger.warn(f"配置できませんでした: {code}", stage="Stage 5")

    violations = validate_all(context, timetable)
    level = logger.error if violations else logger.info
    level(
        f"検証完了: 配置 {len(timetable.placed_codes())} 件 / "
        f"未配置 {len(unplaced)} 件 / 違反 {len(violations)} 件",
        stage="Stage 6",
    )
    for violation in violations:
        logger.error(f"[{violation.rule_id}] {violation.message}", stage="Stage 6")

    return GenerationResult(
        timetable=timetable,
        unplaced=unplaced,
        violations=violations,
        warnings=warnings,
        intensive_codes=intensive_codes,
    )


def apply_inherit_plan(context, timetable, inherit_plan, logger) -> None:
    """踏襲モードで前年度の配置を反映する。"""
    apply_plan(context, timetable, inherit_plan, logger)
