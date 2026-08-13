import pytest

from app.settings_store import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    AppSettings,
    SettingsStore,
)


def build(tmp_path):
    return SettingsStore(tmp_path / ".env", tmp_path / "settings.json")


def test_load_returns_defaults_when_no_file(tmp_path):
    settings = build(tmp_path).load()
    assert settings.model == DEFAULT_MODEL
    assert settings.max_retries == DEFAULT_MAX_RETRIES


def test_save_then_load_roundtrip(tmp_path):
    store = build(tmp_path)
    store.save(AppSettings(model="gemini-2.5-pro", max_retries=5))
    loaded = store.load()
    assert loaded.model == "gemini-2.5-pro"
    assert loaded.max_retries == 5


def test_api_key_is_absent_by_default(tmp_path):
    store = build(tmp_path)
    assert store.get_api_key() is None
    assert store.masked_api_key() is None


def test_set_and_get_api_key(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    assert store.get_api_key() == "AIzaSyEXAMPLE1234567890"


def test_masked_api_key_hides_the_secret(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    masked = store.masked_api_key()
    assert masked == "AIzaSy****"
    assert "EXAMPLE" not in masked


def test_delete_api_key(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    store.delete_api_key()
    assert store.get_api_key() is None


def test_set_api_key_preserves_other_env_entries(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER_VAR=keep-me\n", encoding="utf-8")
    store = SettingsStore(env, tmp_path / "settings.json")
    store.set_api_key("AIzaSyNEW")
    content = env.read_text(encoding="utf-8")
    assert "OTHER_VAR=keep-me" in content
    assert "GEMINI_API_KEY=AIzaSyNEW" in content


def test_replacing_api_key_does_not_duplicate_the_line(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyOLD")
    store.set_api_key("AIzaSyNEW")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert content.count("GEMINI_API_KEY=") == 1
    assert "AIzaSyNEW" in content


def test_max_retries_is_clamped_to_at_least_one(tmp_path):
    store = build(tmp_path)
    store.save(AppSettings(model=DEFAULT_MODEL, max_retries=0))
    assert store.load().max_retries == 1


def test_load_falls_back_to_defaults_on_invalid_json(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json", encoding="utf-8")
    settings = SettingsStore(tmp_path / ".env", settings_path).load()
    assert settings.model == DEFAULT_MODEL
    assert settings.max_retries == DEFAULT_MAX_RETRIES


def test_load_falls_back_to_defaults_when_max_retries_is_not_numeric(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"model": "gemini-2.5-pro", "max_retries": "many"}', encoding="utf-8"
    )
    settings = SettingsStore(tmp_path / ".env", settings_path).load()
    assert settings.model == DEFAULT_MODEL
    assert settings.max_retries == DEFAULT_MAX_RETRIES


@pytest.mark.parametrize("key", ["A", "AAAAA", "AAAAAA", "AAAAAAA"])
def test_short_keys_are_never_fully_exposed(tmp_path, key):
    # 実物の Gemini キーは長いが、検証用の短い値を入れられても全文は出さない
    store = build(tmp_path)
    store.set_api_key(key)
    masked = store.masked_api_key()
    assert masked.endswith("****")
    assert key not in masked
