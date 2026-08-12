import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _prepare():
    from app.models.enums import Category, Department, TeacherKind, Term
    from app.models.subject import Subject
    from app.models.teacher import Teacher
    from app.session_store import SessionData, store

    subjects = [
        Subject(
            code="A1", name="科目甲", base_name="科目甲", department=Department.MANAGEMENT,
            year=1, term=Term.SPRING, quarter=None, category=Category.REQUIRED,
            teacher="専任甲",
        ),
        Subject(
            code="A2", name="科目乙", base_name="科目乙", department=Department.MANAGEMENT,
            year=1, term=Term.SPRING, quarter=None, category=Category.REQUIRED,
            teacher="専任乙",
        ),
    ]
    teachers = {
        "専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="水"),
        "専任乙": Teacher("専任乙", TeacherKind.FULL_TIME),
    }
    session_id = store.create(SessionData(subjects=subjects, teachers=teachers))
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})

    deadline = time.time() + 20
    while time.time() < deadline:
        if client.get(f"/api/result/{session_id}").json()["status"] == "done":
            return session_id
        time.sleep(0.1)
    raise AssertionError("生成が完了しませんでした")


def test_result_includes_subject_metadata():
    session_id = _prepare()
    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    entry = next(p for p in placements if p["code"] == "A1")
    assert entry["name"] == "科目甲"
    assert entry["teacher"] == "専任甲"
    assert entry["department"] == "経営"
    assert len(entry["slots"]) == 1


def test_move_to_free_slot_is_applied():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["金5"]}
    )
    assert response.status_code == 200
    assert response.json()["applied"] is True

    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    entry = next(p for p in placements if p["code"] == "A1")
    assert entry["slots"] == ["金5"]
    assert entry["source"] == "manual"


def test_move_onto_research_day_is_rejected():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["水1"]}
    )
    body = response.json()
    assert body["applied"] is False
    assert [v["rule_id"] for v in body["violations"]] == ["H6"]

    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    assert next(p for p in placements if p["code"] == "A1")["slots"] != ["水1"]


def test_move_rejects_unknown_code():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "Z9", "slots": ["月1"]}
    )
    assert response.status_code == 404


def test_move_rejects_bad_slot_label():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["土1"]}
    )
    assert response.status_code == 400
