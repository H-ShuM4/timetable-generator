"""Stage 0〜6 のオーケストレーション。

Gemini 段階は gemini_placer として注入する。注入しなければ
モックモードと同じ経路になるため、テストに API キーは要らない。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from app.constraints.context import Context, Violation
from app.constraints.linking import linked_group
from app.constraints.validator import validate_all
from app.ingest.pair_linking import link_subjects
from app.ingest.validators import Warning, collect_warnings
from app.logging.session_logger import SessionLogger
from app.models.enums import Category
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timetable import Timetable
from app.scheduler.inherit import InheritPlan, InheritSkip, apply_plan
from app.scheduler.objectives import Weights
from app.scheduler.prelock import prelock
from app.scheduler.repair import repair
from app.scheduler.solver import solve

STAGE_ORDER: tuple[tuple[str, Category], ...] = (
    ("Stage 2", Category.REQUIRED),
    ("Stage 3", Category.ELECTIVE_REQUIRED),
    ("Stage 4", Category.ELECTIVE),
)


class GenerationCancelled(Exception):
    """事務局が生成を中止した。

    **中止したら結果は残さない。** 半端な時間割を「結果」として見せると、
    どこまでが確定でどこからが未確定なのか事務局には判別できない。
    §11 の「生成が例外で終わった場合は成功として見せない」と同じ扱いに
    する。どこまで進んだかはログに残る。
    """


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
    inherit_skips: list[InheritSkip] = field(default_factory=list)
    """踏襲モードで、前年度の枠へ戻せなかった科目とその理由。"""


def release_partial_groups(
    context: Context, timetable: Timetable, pending: list[str]
) -> list[str]:
    """一部だけ置かれた「同じコマに入るべき」科目群を、まとめて外す。

    H4（合同）と H12（前後期）は同一コマを要求する。片方が先に置かれると
    残りはそのコマ以外を選べず、そこが埋まっていれば永久に置けない。
    ソルバーは自分でグループごと置くとき先読みしてこれを避けるが、
    **Gemini が片方だけ置いて残りを未確定にした場合は手遅れになる。**

    実際に起きた 2 件：
      - 合同の経営側を AI が金 1 に置いたが、会計側は朝学習（H13）で
        金 1 に置けなかった
      - 日本語リテラシーⅠ・Ⅱ【再】の 4 科目のうち 3 件が月 2 に入り、
        残る 1 件は後期の月 2 に別の必修があって入れなかった

    そこで置かれているほうを外し、グループ全体をソルバーに委ねる。
    ソルバーは全員が入れるコマだけを候補にするので、同じ行き違いが起きない。
    事務局が曜日時限を決めた枠を含むグループは外さない。
    """
    released: list[str] = []
    for code in sorted(set(pending)):
        subject = context.subjects.get(code)
        if subject is None:
            continue
        group = linked_group(context, subject)
        placed = [c for c in group if timetable.is_placed(c)]
        if not placed:
            continue
        if any(context.subjects[c].fixed_slot is not None for c in group):
            continue
        for member in placed:
            timetable.remove(member)
            released.append(member)
    return sorted(set(released))


def run_pipeline(
    subjects: list[Subject],
    teachers: list[Teacher] | dict[str, Teacher],
    mode: GenerationMode,
    logger: SessionLogger,
    *,
    gemini_placer: GeminiPlacer | None = None,
    inherit_plan: "InheritPlan | None" = None,
    weights: Weights | None = None,
    repair_seconds: float = 0.0,
    should_cancel: Callable[[], bool] | None = None,
) -> GenerationResult:
    logger.info(f"生成を開始します（{mode.label}）", stage="Stage 0")

    def stop_if_cancelled(stage: str) -> None:
        """段の変わり目で中止を確かめる。

        段の途中では止めない。Gemini はチャンクの応答を捨てると無料枠が
        無駄になり、ソルバーと修復は自前で中断点を持っている。
        """
        if should_cancel is not None and should_cancel():
            logger.warn("生成を中止しました", stage=stage)
            raise GenerationCancelled

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

    # 踏襲モードでは、事前ロックにも前年度のコマを希望として渡す。渡さないと
    # 候補の先頭（月曜 1 限寄り）を取り、前年度からいた科目を押し出す。
    # 他のモードには渡さないので挙動は変わらない。
    prefer = None
    if mode is GenerationMode.INHERIT and inherit_plan is not None:
        prefer = {
            code: entry.slots for code, entry in inherit_plan.previous_slots.items()
        }
    timetable, leftover = prelock(context, subjects, prefer=prefer)
    logger.info(f"事前ロック {len(timetable.placed_codes())} 件", stage="Stage 1")
    for code in leftover:
        logger.warn(f"非常勤の出勤可能コマに空きがありません: {code}", stage="Stage 1")

    inherit_skips: list[InheritSkip] = []
    if mode is GenerationMode.INHERIT and inherit_plan is not None:
        inherit_skips = apply_inherit_plan(context, timetable, inherit_plan, logger)

    pending = [
        s.code for s in subjects
        if not s.is_intensive and not timetable.is_placed(s.code)
    ]

    if mode is not GenerationMode.MOCK and gemini_placer is not None:
        for stage_name, category in STAGE_ORDER:
            stop_if_cancelled(stage_name)
            codes = [c for c in pending if context.subjects[c].category is category]
            if not codes:
                continue
            logger.info(f"{category.value} {len(codes)} 件を配置します", stage=stage_name)
            failed = gemini_placer(context, timetable, codes, logger)
            placed = len(codes) - len(failed)
            logger.info(f"{placed} 件を配置、{len(failed)} 件が未確定", stage=stage_name)
            pending = [c for c in pending if not timetable.is_placed(c)]

    released = release_partial_groups(context, timetable, pending)
    if released:
        logger.info(
            f"同じコマに入るべき科目が分かれていたため、{len(released)} 件を置き直します",
            stage="Stage 5",
        )
        pending = sorted(set(pending) | set(released))

    stop_if_cancelled("Stage 5")
    if pending:
        logger.info(f"ソルバーで {len(pending)} 件を補完します", stage="Stage 5")
    unplaced = solve(context, timetable, pending, should_cancel=should_cancel)
    stop_if_cancelled("Stage 5")
    for code in unplaced:
        logger.warn(f"配置できませんでした: {code}", stage="Stage 5")

    if repair_seconds > 0 and weights is not None and not weights.is_idle:
        logger.info("配置を見直します", stage="Stage 5.5")
        repair(context, timetable, weights, seconds=repair_seconds, logger=logger,
               should_cancel=should_cancel)
        stop_if_cancelled("Stage 5.5")

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
        inherit_skips=inherit_skips,
    )


def apply_inherit_plan(context, timetable, inherit_plan, logger) -> list[InheritSkip]:
    """踏襲モードで前年度の配置を反映し、戻せなかった科目を返す。"""
    return apply_plan(context, timetable, inherit_plan, logger)
