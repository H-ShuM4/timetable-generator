import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings_store import SettingsStore


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """テストが実際の .env を書き換えないよう差し替える。"""
    import app.api.settings as settings_api

    store = SettingsStore(tmp_path / ".env", tmp_path / "settings.json")
    monkeypatch.setattr(settings_api, "store", store)
    return store


client = TestClient(app)


def test_get_settings_returns_defaults():
    body = client.get("/api/settings").json()
    assert body["model"] == "gemini-2.5-flash"
    assert body["max_retries"] == 3
    assert body["has_api_key"] is False
    assert body["api_key_masked"] is None


def test_put_settings_persists_values():
    client.put("/api/settings", json={"model": "gemini-2.5-pro", "max_retries": 5})
    body = client.get("/api/settings").json()
    assert body["model"] == "gemini-2.5-pro"
    assert body["max_retries"] == 5


def test_put_api_key_then_get_returns_masked_only():
    client.put("/api/settings/api-key", json={"api_key": "AIzaSyEXAMPLE1234567890"})
    body = client.get("/api/settings").json()
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "AIzaSy****"
    assert "EXAMPLE" not in str(body)


def test_delete_api_key():
    client.put("/api/settings/api-key", json={"api_key": "AIzaSyEXAMPLE1234567890"})
    assert client.delete("/api/settings/api-key").status_code == 200
    assert client.get("/api/settings").json()["has_api_key"] is False


def test_put_settings_rejects_zero_retries():
    response = client.put("/api/settings", json={
        "model": "gemini-2.5-flash", "max_retries": 0
    })
    assert response.status_code == 422
