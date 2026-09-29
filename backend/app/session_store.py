"""読み込んだデータと生成結果をセッション単位で保持する。

**メモリ上の辞書だけでは足りない。** AI モードは数十分かかり
Gemini の無料枠も消費するため、サーバの再起動やブラウザの再読み込みで
結果が消えると、事務局はアップロードからやり直すことになる。

そこでアップロードされた Excel をセッションごとに保存し、復元時は
**同じ読み込み処理を通し直して**から結果 JSON を重ねる。科目や教員を
別形式でもう一度持つより、読み込みが 1 経路のままで済む。制約違反は
保存値を使わず再計算する。保存後に制約を変更した場合、古い判定を
表示するほうが害が大きい。
"""
import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.ingest.session_builder import load_session_data
from app.ingest.validators import Warning
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.paths import storage_root
from app.scheduler.inherit import InheritSkip, PreviousEntry
from app.scheduler.pipeline import GenerationResult

SESSIONS_DIR = storage_root() / "data" / "sessions"

MAX_SESSIONS = 10
"""保存しておくセッション数。古いものから消す。

1 セッションで Excel 2〜4 本と結果 JSON を抱えるため、放置すると
際限なく増える。事務局が遡って見たいのはせいぜい直近の数回である。
読込画面の一覧もこの数だけ並ぶので、多すぎると選びにくい。
"""

FILE_ROLES = ("curriculum", "teachers", "previous_curriculum", "previous_teachers")


@dataclass(slots=True)
class SessionData:
    subjects: list[Subject]
    teachers: dict[str, Teacher]
    warnings: list[Warning] = field(default_factory=list)
    previous_entries: dict[str, PreviousEntry] = field(default_factory=dict)
    previous_teachers: dict[str, Teacher] = field(default_factory=dict)
    result: GenerationResult | None = None
    logger: SessionLogger | None = None
    running: bool = False
    error: str | None = None
    cancelled: bool = False
    """直前の生成が事務局の中止で終わったか。失敗とは区別する。"""
    cancel_event: threading.Event | None = None
    """生成中だけ立つ。中止要求はこれを set して伝える。"""

    @classmethod
    def from_loaded(cls, loaded) -> "SessionData":
        """Excel から読み取った内容（LoadedData）をセッションに載せる。

        **詰め替えはここ 1 か所だけにする。** アップロードのときと復元の
        ときで同じ変換をするので、2 箇所に書くと読み取る項目が増えたときに
        片方だけ直し忘れる。
        """
        return cls(
            subjects=loaded.subjects,
            teachers=loaded.teachers,
            warnings=loaded.warnings,
            previous_entries=loaded.previous_entries,
            previous_teachers=loaded.previous_teachers,
        )

    @property
    def context(self) -> Context:
        return Context.from_lists(self.subjects, self.teachers)


class SessionStore:
    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions: dict[str, SessionData] = {}
        self._dir = Path(sessions_dir) if sessions_dir else SESSIONS_DIR

    # ------------------------------------------------------------------ 作成

    def create(self, data: SessionData, files: dict[str, tuple] | None = None) -> str:
        """files は 役割 → (保存元のパス, 事務局が選んだファイル名)。

        パスはアップロードを受けた一時ファイルなので、名前は控えても
        意味がない。一覧で何を読んだか分かるよう、元の名前を別に受け取る。
        """
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = data
        if files:
            self._store_files(session_id, files)
        self._prune()
        return session_id

    def _store_files(self, session_id: str, files: dict[str, tuple]) -> None:
        directory = self._dir / session_id / "files"
        directory.mkdir(parents=True, exist_ok=True)
        stored = {}
        for role, entry in files.items():
            if role not in FILE_ROLES or entry is None:
                continue
            path, original_name = entry
            shutil.copyfile(path, directory / f"{role}.xlsx")
            stored[role] = original_name or Path(path).name
        (self._dir / session_id / "meta.json").write_text(
            json.dumps(
                {"created_at": datetime.now().isoformat(timespec="seconds"),
                 "files": stored},
                ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prune(self) -> None:
        directories = sorted(
            (p for p in self._dir.glob("*") if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in directories[MAX_SESSIONS:]:
            data = self._sessions.get(stale.name)
            if data is not None and data.running:
                continue  # 生成中のセッションは消さない
            shutil.rmtree(stale, ignore_errors=True)
            self._sessions.pop(stale.name, None)

    # ------------------------------------------------------------------ 取得

    def get(self, session_id: str) -> SessionData | None:
        data = self._sessions.get(session_id)
        if data is not None:
            return data
        return self._restore(session_id)

    def _restore(self, session_id: str) -> SessionData | None:
        """保存した Excel を読み直してセッションを組み立てる。

        復元に失敗しても None を返すだけにする。壊れたセッションが
        1 つあるせいで画面が開かなくなるほうが困る。
        """
        directory = self._dir / session_id
        if not (directory / "files" / "curriculum.xlsx").exists():
            return None

        logger = SessionLogger(f"restore-{session_id}")
        try:
            data = self._read_session_files(directory, logger)
        except Exception as error:
            logger.error(f"セッション {session_id} を復元できませんでした: {error}")
            return None
        finally:
            logger.close()

        self._apply_saved_result(directory, data)
        self._sessions[session_id] = data
        return data

    def _read_session_files(self, directory: Path, logger: SessionLogger) -> SessionData:
        """保存した Excel を、アップロード時とまったく同じ手順で読み直す。"""
        files = directory / "files"

        def optional(name: str) -> Path | None:
            path = files / f"{name}.xlsx"
            return path if path.exists() else None

        loaded = load_session_data(
            files / "curriculum.xlsx",
            files / "teachers.xlsx",
            logger,
            previous_curriculum=optional("previous_curriculum"),
            previous_teachers=optional("previous_teachers"),
        )
        return SessionData.from_loaded(loaded)

    def _apply_saved_result(self, directory: Path, data: SessionData) -> None:
        path = directory / "result.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        timetable = Timetable()
        known = {s.code for s in data.subjects}
        for item in payload.get("assignments", []):
            if item["code"] not in known:
                continue  # Excel が差し替わって消えた科目
            timetable.place(
                item["code"],
                tuple(TimeSlot(s[:-1], int(s[-1])) for s in item["slots"]),
                AssignmentSource(item["source"]),
            )
        context = data.context
        data.result = GenerationResult(
            timetable=timetable,
            unplaced=[c for c in payload.get("unplaced", []) if c in known],
            violations=validate_all(context, timetable),
            warnings=data.warnings,
            intensive_codes=[c for c in payload.get("intensive", []) if c in known],
            inherit_skips=[
                InheritSkip(
                    code=item["code"], rule_id=item["rule_id"],
                    message=item["message"], related_code=item.get("related_code"),
                )
                for item in payload.get("inherit_skips", [])
                if item.get("code") in known
            ],
        )

    # ------------------------------------------------------------------ 保存

    def save_result(self, session_id: str) -> Path | None:
        data = self._sessions.get(session_id)
        if data is None or data.result is None:
            return None

        payload = {
            "session_id": session_id,
            "assignments": [
                {
                    "code": code,
                    "slots": [f"{s.day}{s.period}" for s in assignment.slots],
                    "source": assignment.source.value,
                }
                for code, assignment in data.result.timetable.assignments.items()
            ],
            "unplaced": data.result.unplaced,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "subject_code": v.subject_code,
                    "message": v.message,
                    "related_code": v.related_code,
                }
                for v in data.result.violations
            ],
            "intensive": data.result.intensive_codes,
            # 生成のときにしか分からない記録で、あとから計算し直せない。
            # 制約違反と違って再計算しないので、そのまま保存する。
            "inherit_skips": [
                {
                    "code": s.code,
                    "rule_id": s.rule_id,
                    "message": s.message,
                    "related_code": s.related_code,
                }
                for s in data.result.inherit_skips
            ],
        }
        directory = self._dir / session_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "result.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ 一覧

    def list_sessions(self) -> list[dict]:
        """新しい順のセッション一覧。画面から選び直せるようにする。"""
        rows = []
        for directory in self._dir.glob("*"):
            if not directory.is_dir() or not (directory / "files").exists():
                continue
            meta = {}
            try:
                meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
            rows.append({
                "session_id": directory.name,
                "created_at": meta.get("created_at", ""),
                "files": meta.get("files", {}),
                "has_result": (directory / "result.json").exists(),
            })
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)


store = SessionStore()
