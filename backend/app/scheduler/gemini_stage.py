"""Stage 2〜4: Gemini にチャンク単位で配置させ、検証して差し戻す。

成功済みの配置は再送しない。差し戻すのは違反した科目だけなので、
再試行してもトークンが線形に膨らまない。
"""
import time
from collections import defaultdict

from app.constraints.context import Context
from app.constraints.validator import check_placement
from app.gemini.client import GeminiClient, GeminiError
from app.gemini.prompts import build_placement_prompt, parse_placement_response
from app.logging.session_logger import SessionLogger
from app.models.timetable import AssignmentSource, Timetable


def chunk_codes(context: Context, codes: list[str]) -> list[tuple[str, list[str]]]:
    """学科 × 開講期 × コースでチャンクに割る。"""
    groups: dict[tuple, list[str]] = defaultdict(list)
    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        key = (
            subject.department.value,
            subject.term.value,
            tuple(sorted(subject.courses)),
        )
        groups[key].append(code)

    chunks: list[tuple[str, list[str]]] = []
    for key, group_codes in groups.items():
        department, term, courses = key
        label = f"{department}・{term}"
        if courses:
            label += f"・{'/'.join(courses)}"
        chunks.append((label, group_codes))
    return chunks


def make_gemini_placer(client: GeminiClient, max_retries: int):
    """pipeline.run_pipeline に渡す gemini_placer を組み立てる。"""

    def place(
        context: Context, timetable: Timetable, codes: list[str], logger: SessionLogger
    ) -> list[str]:
        unplaced: list[str] = []
        for label, chunk in chunk_codes(context, codes):
            unplaced.extend(_place_chunk(context, timetable, chunk, label, logger))
        return unplaced

    def _place_chunk(
        context: Context,
        timetable: Timetable,
        chunk: list[str],
        label: str,
        logger: SessionLogger,
    ) -> list[str]:
        remaining = [c for c in chunk if not timetable.is_placed(c)]
        feedback: list[str] = []

        for attempt in range(1, max_retries + 1):
            if not remaining:
                break

            prompt = build_placement_prompt(context, timetable, remaining, feedback=feedback)
            logger.info(
                f"{label}: {len(remaining)} 件を送信（{attempt}/{max_retries} 回目、"
                f"{len(prompt)} 文字）",
                stage="Gemini",
            )

            started = time.monotonic()
            try:
                text = client.generate(prompt)
            except GeminiError as error:
                logger.warn(f"{label}: 呼び出しに失敗しました（{error}）", stage="Gemini")
                continue
            logger.info(
                f"{label}: 応答を受信（{time.monotonic() - started:.1f}秒）", stage="Gemini"
            )

            try:
                parsed = parse_placement_response(text)
            except ValueError as error:
                logger.warn(f"{label}: 応答を解釈できません（{error}）", stage="Gemini")
                feedback = ["応答が指定の JSON 形式ではありませんでした"]
                continue

            feedback = []
            for code in list(remaining):
                slots = parsed.get(code)
                if not slots:
                    feedback.append(f"{code}: 配置が返りませんでした")
                    continue
                subject = context.subjects[code]
                violations = check_placement(context, timetable, subject, slots)
                if violations:
                    for violation in violations:
                        feedback.append(
                            f"{code}: [{violation.rule_id}] {violation.message}"
                        )
                    continue
                timetable.place(code, slots, AssignmentSource.GEMINI)

            remaining = [c for c in remaining if not timetable.is_placed(c)]
            if remaining:
                logger.warn(
                    f"{label}: {len(remaining)} 件が違反のため差し戻します", stage="Gemini"
                )

        return remaining

    return place
