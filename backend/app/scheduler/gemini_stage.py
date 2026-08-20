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
    """学科 × 年次 × 開講期でチャンクに割る。

    年次を鍵に含めるのは、H2 と H3 が「学科 × 年次」で衝突を判定する
    ためである。年次で切ると各チャンクが互いに衝突しうる科目だけの塊に
    なり、Gemini が考慮すべき範囲とチャンクの範囲が一致する。

    **コースを鍵に含めない。** H2・H3 はコースを見ないので、コースで
    細分しても衝突の判定範囲は変わらず、リクエスト数だけが増える。
    実データではコースを鍵から外すことでチャンクが 54 個から 20 個へ
    減った。Gemini の無料枠は 1 モデルあたり 1 日 20 リクエストなので、
    この差が「1 回の生成が完走できるかどうか」を分ける。

    併合してもプロンプトは最大 6,429 文字（併合前 4,708 文字）にしか
    ならず、モデルの入力上限に対して十分小さい。
    """
    groups: dict[tuple, list[str]] = defaultdict(list)
    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        key = (subject.department.value, subject.year, subject.term.value)
        groups[key].append(code)

    return [
        (f"{department}{year}年・{term}", group_codes)
        for (department, year, term), group_codes in groups.items()
    ]


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
            except Exception as error:  # 想定外の例外でも生成全体を止めない
                logger.error(
                    f"{label}: 想定外のエラーが発生しました（{type(error).__name__}: {error}）",
                    stage="Gemini",
                )
                continue
            # どのモデルが応答したかは呼び出し**後**に読む。枠切れで別の
            # モデルへ切り替わった場合、送信前に読んだ名前とは食い違う。
            # 単一モデルではこの属性が無く、ログは従来どおりになる。
            model = getattr(client, "current_model", None)
            answered_by = f"、{model}" if model else ""
            logger.info(
                f"{label}: 応答を受信（{time.monotonic() - started:.1f}秒{answered_by}）",
                stage="Gemini",
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
