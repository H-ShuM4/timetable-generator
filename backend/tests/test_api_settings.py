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


def test_settings_default_to_no_fallback_models():
    assert client.get("/api/settings").json()["fallback_models"] == []


def test_put_settings_persists_fallback_models():
    body = client.put("/api/settings", json={
        "model": "gemini-3.7-flash",
        "max_retries": 3,
        "fallback_models": ["gemini-3.6-flash", "gemini-3.5-flash"],
    }).json()
    assert body["fallback_models"] == ["gemini-3.6-flash", "gemini-3.5-flash"]
    assert client.get("/api/settings").json()["fallback_models"] == [
        "gemini-3.6-flash", "gemini-3.5-flash"
    ]


def test_omitting_fallback_models_clears_them():
    """事務局が設定を保存し直したときに開発用の指定が残らないようにする。"""
    client.put("/api/settings", json={
        "model": "gemini-3.7-flash",
        "max_retries": 3,
        "fallback_models": ["gemini-3.6-flash"],
    })
    body = client.put("/api/settings", json={
        "model": "gemini-3.7-flash", "max_retries": 3,
    }).json()
    assert body["fallback_models"] == []


def test_fallback_models_cannot_repeat_the_primary_model():
    body = client.put("/api/settings", json={
        "model": "gemini-3.7-flash",
        "max_retries": 3,
        "fallback_models": ["gemini-3.7-flash", "gemini-3.6-flash"],
    }).json()
    assert body["fallback_models"] == ["gemini-3.6-flash"]
