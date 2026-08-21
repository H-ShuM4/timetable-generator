"""Excel 4 本からセッションの中身を組み立てる。

アップロード時と復元時の両方がここを通る。読み込みから前処理までを
1 箇所にまとめておかないと、片方だけが古くなる。実際 `assign_pair_ids`
を足したとき、テストのフィクスチャが呼び忘れて本番と違う条件で
走っていた。
"""
from dataclasses import dataclass
from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum_rows
from app.ingest.markitdown_fallback import read_curriculum_with_fallback
from app.ingest.pair_linking import link_subjects
from app.ingest.teacher_reader import read_teachers
from app.ingest.validators import Warning, check_partial_slots, collect_warnings
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.scheduler.inherit import PreviousEntry, read_previous_timetable


@dataclass(slots=True)
class LoadedData:
    """Excel から読み取った内容。セッションに載せる前の素材。"""

    subjects: list[Subject]
    teachers: dict[str, Teacher]
    warnings: list[Warning]
    previous_entries: dict[str, PreviousEntry]
    previous_teachers: dict[str, Teacher]


def read_curriculum_file(path: str | Path, logger: SessionLogger) -> list[Subject]:
    """カリキュラム一覧を読む。壊れた xlsx は MarkItDown で読み直す。"""
    return read_curriculum_with_fallback(path, logger)


def load_session_data(
    curriculum: str | Path,
    teachers: str | Path,
    logger: SessionLogger,
    *,
    previous_curriculum: str | Path | None = None,
    previous_teachers: str | Path | None = None,
    read: object = None,
) -> LoadedData:
    """4 本の Excel を読み、結び付けと検査まで済ませて返す。

    read には「ラベルを添えて読む」関数を渡せる。アップロード経路は
    どのファイルが原因かを 400 で返すためにこれを使う。渡さなければ
    そのまま呼ぶ。
    """
    def plain(_label, action):
        return action()

    step = read if read is not None else plain

    subjects = step("curriculum", lambda: read_curriculum_file(curriculum, logger))
    partial = step("curriculum", lambda: check_partial_slots(read_curriculum_rows(curriculum)))
    teacher_map = step("teachers", lambda: read_teachers(teachers))

    previous_entries: dict[str, PreviousEntry] = {}
    if previous_curriculum is not None:
        previous_entries = step(
            "previous_curriculum", lambda: read_previous_timetable(previous_curriculum)
        )
    previous_teacher_map: dict[str, Teacher] = {}
    if previous_teachers is not None:
        previous_teacher_map = step(
            "previous_teachers", lambda: read_teachers(previous_teachers)
        )

    mismatches = link_subjects(subjects)
    return LoadedData(
        subjects=subjects,
        teachers=teacher_map,
        warnings=collect_warnings(subjects, teacher_map, mismatches) + partial,
        previous_entries=previous_entries,
        previous_teachers=previous_teacher_map,
    )
