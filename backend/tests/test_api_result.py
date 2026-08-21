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


def _prepare_joint():
    """合同ペア（経営側・会計側）を同じコマに置いたセッションを作る。"""
    from app.models.enums import Category, Department, TeacherKind, Term
    from app.models.subject import Subject
    from app.models.teacher import Teacher
    from app.models.timeslot import TimeSlot
    from app.models.timetable import AssignmentSource
    from app.scheduler.pipeline import GenerationResult
    from app.models.timetable import Timetable
    from app.session_store import SessionData, store

    def make(code, dept, joint_id=None, teacher="専任甲"):
        return Subject(
            code=code, name=code, base_name="合同科目", department=dept, year=1,
            term=Term.SPRING, quarter=None, category=Category.ELECTIVE,
            teacher=teacher, joint_id=joint_id,
        )

    a = make("A1", Department.ACCOUNTING, joint_id="J001")
    b = make("B1", Department.MANAGEMENT, joint_id="J001")
    blocker = make("B9", Department.MANAGEMENT, teacher="専任甲")
    teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME)}

    timetable = Timetable()
    timetable.place("A1", (TimeSlot("月", 1),), AssignmentSource.SOLVER)
    timetable.place("B1", (TimeSlot("月", 1),), AssignmentSource.SOLVER)
    timetable.place("B9", (TimeSlot("水", 3),), AssignmentSource.SOLVER)

    data = SessionData(subjects=[a, b, blocker], teachers=teachers)
    data.result = GenerationResult(timetable=timetable)
    return store.create(data), data


def test_moving_one_side_of_a_joint_pair_moves_both():
    session_id, data = _prepare_joint()

    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "B1", "slots": ["木4"]}
    )
    assert response.status_code == 200
    assert response.json()["applied"] is True

    placements = {p["code"]: p for p in client.get(f"/api/result/{session_id}").json()["placements"]}
    assert placements["B1"]["slots"] == ["木4"]
    assert placements["A1"]["slots"] == ["木4"], "会計側も一緒に動くこと"
    assert placements["A1"]["source"] == "manual"


def test_a_joint_move_blocked_for_the_partner_moves_nothing():
    session_id, data = _prepare_joint()

    # 水3 には同じ教員の別科目 B9 が居るので H1 で弾かれる
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["水3"]}
    )
    body = response.json()
    assert body["applied"] is False
    assert "H1" in {v["rule_id"] for v in body["violations"]}

    placements = {p["code"]: p for p in client.get(f"/api/result/{session_id}").json()["placements"]}
    assert placements["A1"]["slots"] == ["月1"], "拒否されたら元の位置のまま"
    assert placements["B1"]["slots"] == ["月1"]
    assert placements["A1"]["source"] == "solver", "source も元のまま"


def test_an_unplaced_subject_can_be_placed_by_hand():
    """未配置科目を画面からドラッグで置けるようにするため、移動 API は
    まだ置かれていない科目コードも受け付ける。"""
    from app.session_store import store

    session_id = _prepare()
    data = store.get(session_id)
    # A2 をいったん外し、未配置として扱う
    data.result.timetable.remove("A2")
    data.result.unplaced = ["A2"]

    body = client.post(
        f"/api/result/{session_id}/move", json={"code": "A2", "slots": ["木4"]}
    ).json()
    assert body["applied"] is True
    assert [str(s) for s in data.result.timetable.slot_of("A2")] == ["木4"]


def test_placing_an_unplaced_subject_still_respects_constraints():
    from app.session_store import store

    session_id = _prepare()
    data = store.get(session_id)
    occupied = data.result.timetable.slot_of("A1")
    data.result.timetable.remove("A2")
    data.result.unplaced = ["A2"]

    label = f"{occupied[0].day}{occupied[0].period}"
    body = client.post(
        f"/api/result/{session_id}/move", json={"code": "A2", "slots": [label]}
    ).json()
    assert body["applied"] is False
    assert [v["rule_id"] for v in body["violations"]] == ["H2"]
    assert not data.result.timetable.slot_of("A2")
