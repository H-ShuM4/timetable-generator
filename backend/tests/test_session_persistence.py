"""セッションの保存・復元・保持件数。

生成には数十分と Gemini の無料枠がかかるため、再起動や再読み込みで
結果が消えないことを保証する。
"""
from pathlib import Path

import pytest

from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.pipeline import GenerationResult
from app.session_store import SessionData, SessionStore

_ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = _ROOT / "カリキュラム一覧(整形済み).xlsx"
TEACHERS = _ROOT / "教員一覧(整形済み).xlsx"


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path)


@pytest.fixture
def uploaded(store):
    """アップロード直後と同じ状態を作る。"""
    from app.ingest.curriculum_reader import read_curriculum
    from app.ingest.joint_pairing import assign_joint_ids
    from app.ingest.pair_linking import assign_pair_ids
    from app.ingest.teacher_reader import read_teachers

    subjects = read_curriculum(CURRICULUM)
    assign_joint_ids(subjects)
    assign_pair_ids(subjects)
    data = SessionData(subjects=subjects, teachers=read_teachers(TEACHERS))
    session_id = store.create(data, {
        "curriculum": (CURRICULUM, "カリキュラム一覧.xlsx"),
        "teachers": (TEACHERS, "教員一覧.xlsx"),
    })
    return session_id, data


def test_a_session_survives_losing_the_in_memory_copy(store, uploaded):
    session_id, _ = uploaded
    store._sessions.clear()  # サーバ再起動と同じ状態

    restored = store.get(session_id)
    assert restored is not None
    assert len(restored.subjects) == 658
    assert restored.teachers


def test_pair_and_joint_links_are_rebuilt_on_restore(store, uploaded):
    session_id, _ = uploaded
    store._sessions.clear()

    restored = store.get(session_id)
    assert any(s.joint_id for s in restored.subjects)
    assert any(s.pair_id for s in restored.subjects)


def test_a_saved_result_comes_back(store, uploaded):
    session_id, data = uploaded
    timetable = Timetable()
    code = data.subjects[0].code
    timetable.place(code, (TimeSlot("水", 3),), AssignmentSource.SOLVER)
    data.result = GenerationResult(timetable=timetable, unplaced=[data.subjects[1].code])
    store.save_result(session_id)
    store._sessions.clear()

    restored = store.get(session_id)
    assert restored.result is not None
    assert restored.result.timetable.slot_of(code) == (TimeSlot("水", 3),)
    assert restored.result.unplaced == [data.subjects[1].code]


def test_violations_are_recomputed_rather_than_trusted(store, uploaded):
    """保存後に制約を変えても、表示されるのは今の判定であること。"""
    session_id, data = uploaded
    data.result = GenerationResult(timetable=Timetable())
    store.save_result(session_id)
    path = store._dir / session_id / "result.json"
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["violations"] = [
        {"rule_id": "H99", "subject_code": "X", "message": "古い判定", "related_code": None}
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store._sessions.clear()

    assert store.get(session_id).result.violations == []


def test_an_unknown_session_is_not_invented(store):
    assert store.get("deadbeef0000") is None


def test_old_sessions_are_deleted(store, monkeypatch):
    import app.session_store as module

    monkeypatch.setattr(module, "MAX_SESSIONS", 3)
    ids = []
    for _ in range(5):
        data = SessionData(subjects=[], teachers={})
        ids.append(store.create(data, {
            "curriculum": (CURRICULUM, "c.xlsx"), "teachers": (TEACHERS, "t.xlsx"),
        }))

    remaining = {row["session_id"] for row in store.list_sessions()}
    assert len(remaining) == 3
    assert set(ids[-3:]) == remaining


def test_the_listing_is_newest_first(store, uploaded):
    session_id, _ = uploaded
    rows = store.list_sessions()
    assert rows[0]["session_id"] == session_id
    # 一時ファイル名ではなく、事務局が選んだ名前が残ること
    assert rows[0]["files"] == {
        "curriculum": "カリキュラム一覧.xlsx", "teachers": "教員一覧.xlsx"
    }
    assert rows[0]["has_result"] is False


def test_a_running_session_is_not_deleted_by_pruning(store, monkeypatch):
    """生成には数十分かかる。その間に古い扱いになっても消してはいけない。"""
    import app.session_store as module

    monkeypatch.setattr(module, "MAX_SESSIONS", 1)
    busy = SessionData(subjects=[], teachers={})
    busy.running = True
    busy_id = store.create(busy, {"curriculum": (CURRICULUM, "c.xlsx"),
                                  "teachers": (TEACHERS, "t.xlsx")})
    store.create(SessionData(subjects=[], teachers={}),
                 {"curriculum": (CURRICULUM, "c.xlsx"), "teachers": (TEACHERS, "t.xlsx")})

    assert busy_id in {row["session_id"] for row in store.list_sessions()}
