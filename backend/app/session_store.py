"""読み込んだデータと生成結果をセッション単位で保持する。

生成結果は data/sessions/<id>.json にも書き出し、サーバを再起動しても
中身を目視で確認できるようにする。
"""
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.constraints.context import Context
from app.ingest.validators import Warning
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.scheduler.inherit import PreviousEntry
from app.scheduler.pipeline import GenerationResult

SESSIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions"


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

    @property
    def context(self) -> Context:
        return Context.from_lists(self.subjects, self.teachers)


class SessionStore:
    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions: dict[str, SessionData] = {}
        self._dir = Path(sessions_dir) if sessions_dir else SESSIONS_DIR

    def create(self, data: SessionData) -> str:
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = data
        return session_id

    def get(self, session_id: str) -> SessionData | None:
        return self._sessions.get(session_id)

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
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{session_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


store = SessionStore()
