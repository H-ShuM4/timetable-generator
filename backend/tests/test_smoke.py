from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_imports_work():
    import fastapi
    import openpyxl
    assert fastapi is not None
    assert openpyxl is not None


def test_static_files_must_be_revalidated():
    """ブラウザが古い JS を掴んだまま新機能が出ない事故を防ぐ。"""
    response = client.get("/js/settings.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_static_files_still_serve_their_content():
    assert "FALLBACK_CANDIDATES" in client.get("/js/settings.js").text
