import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _upload_small(monkeypatch):
    """実データは大きいので、少数の科目を直接セッションに入れる。"""
    from app.models.enums import Category, Department, Term
    from app.models.subject import Subject
    from app.session_store import SessionData, store

    subjects = [
        Subject(
            code=f"A{i}", name=f"科目{i}", base_name=f"科目{i}",
            department=Department.MANAGEMENT, year=1, term=Term.SPRING, quarter=None,
            category=Category.REQUIRED, teacher=f"教員{i}",
        )
        for i in range(4)
    ]
    return store.create(SessionData(subjects=subjects, teachers={}))


def _wait_for_completion(session_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/result/{session_id}")
        if response.status_code == 200 and response.json()["status"] == "done":
            return response.json()
        time.sleep(0.1)
    raise AssertionError("生成が完了しませんでした")


def test_generate_in_mock_mode_completes(monkeypatch):
    session_id = _upload_small(monkeypatch)
    response = client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    assert response.status_code == 202

    body = _wait_for_completion(session_id)
    assert len(body["placements"]) == 4
    assert body["violations"] == []


def test_generate_returns_404_for_unknown_session():
    response = client.post("/api/generate/does-not-exist", json={"mode": "mock"})
    assert response.status_code == 404


def test_optimize_falls_back_to_mock_without_api_key(monkeypatch, tmp_path):
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    monkeypatch.setattr(
        generate_api, "settings_store",
        SettingsStore(tmp_path / ".env", tmp_path / "settings.json"),
    )
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "optimize"})

    body = _wait_for_completion(session_id)
    assert len(body["placements"]) == 4
    assert all(p["source"] == "solver" for p in body["placements"])


def test_stream_delivers_log_events(monkeypatch):
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})

    with client.stream("GET", f"/api/generate/{session_id}/stream") as stream:
        text = "".join(chunk for chunk in stream.iter_text())
    assert "Stage 0" in text
    assert "event: done" in text


def test_export_returns_xlsx(monkeypatch):
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    response = client.get(f"/api/export/{session_id}")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx は zip 形式


def test_export_before_generation_returns_409(monkeypatch):
    session_id = _upload_small(monkeypatch)
    assert client.get(f"/api/export/{session_id}").status_code == 409
