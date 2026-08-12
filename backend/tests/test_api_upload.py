from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "カリキュラム一覧(整形済み).xlsx"
TEACHERS = ROOT / "教員一覧(整形済み).xlsx"

client = TestClient(app)


def _upload():
    with CURRICULUM.open("rb") as curriculum, TEACHERS.open("rb") as teachers:
        return client.post(
            "/api/upload",
            files={
                "curriculum": ("c.xlsx", curriculum, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
            },
        )


def test_upload_returns_session_id_and_summary():
    response = _upload()
    assert response.status_code == 200
    body = response.json()

    assert body["session_id"]
    assert body["summary"]["subject_count"] == 658
    assert body["summary"]["teacher_count"] == 99
    assert body["summary"]["intensive_count"] == 45


def test_upload_summary_breaks_down_by_department_and_category():
    body = _upload().json()
    assert body["summary"]["by_department"]["経営"] == 262
    assert body["summary"]["by_category"]["必修"] > 0
    assert body["summary"]["quarter_count"] == 47


def test_upload_returns_warnings():
    body = _upload().json()
    kinds = {w["kind"] for w in body["warnings"]}
    assert "missing_availability" in kinds


def test_upload_rejects_broken_workbook(tmp_path):
    import openpyxl

    broken = tmp_path / "broken.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["適当な列"])
    workbook.save(broken)

    with broken.open("rb") as bad, TEACHERS.open("rb") as teachers:
        response = client.post(
            "/api/upload",
            files={
                "curriculum": ("b.xlsx", bad, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
            },
        )
    assert response.status_code == 400
    assert "想定外" in response.json()["detail"]


def test_upload_rejects_a_broken_teacher_file(tmp_path):
    import openpyxl

    broken = tmp_path / "broken_teachers.xlsx"
    broken.write_bytes(b"this is not a workbook")

    with CURRICULUM.open("rb") as curriculum, broken.open("rb") as bad:
        response = client.post(
            "/api/upload",
            files={
                "curriculum": ("c.xlsx", curriculum, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", bad, "application/vnd.ms-excel"),
            },
        )
    # どのファイルが原因かが分かること。スタックトレースを返さないこと
    assert response.status_code == 400
    assert "教員一覧" in response.json()["detail"]


def test_upload_accepts_previous_year_files():
    with (
        CURRICULUM.open("rb") as curriculum,
        TEACHERS.open("rb") as teachers,
        CURRICULUM.open("rb") as previous_curriculum,
        TEACHERS.open("rb") as previous_teachers,
    ):
        response = client.post(
            "/api/upload",
            files={
                "curriculum": ("c.xlsx", curriculum, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
                "previous_curriculum": ("pc.xlsx", previous_curriculum, "application/vnd.ms-excel"),
                "previous_teachers": ("pt.xlsx", previous_teachers, "application/vnd.ms-excel"),
            },
        )
    assert response.status_code == 200
    assert response.json()["summary"]["has_previous_year"] is True
