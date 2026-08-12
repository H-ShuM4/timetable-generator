"""API キーと生成設定の永続化。

API キーは .env、それ以外は data/settings.json に置く。
フロントへ返すのはマスク済みの文字列だけで、全文は返さない。
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

API_KEY_NAME = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_RETRIES = 3
VISIBLE_PREFIX_LENGTH = 6

_BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = _BACKEND_DIR / ".env"
DEFAULT_SETTINGS_PATH = _BACKEND_DIR / "data" / "settings.json"


@dataclass(slots=True)
class AppSettings:
    model: str = DEFAULT_MODEL
    max_retries: int = DEFAULT_MAX_RETRIES

    def to_dict(self) -> dict:
        return asdict(self)


class SettingsStore:
    def __init__(
        self, env_path: Path | None = None, settings_path: Path | None = None
    ) -> None:
        self.env_path = Path(env_path) if env_path else DEFAULT_ENV_PATH
        self.settings_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()
        raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        return AppSettings(
            model=raw.get("model", DEFAULT_MODEL) or DEFAULT_MODEL,
            max_retries=max(1, int(raw.get("max_retries", DEFAULT_MAX_RETRIES))),
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.to_dict()
        payload["max_retries"] = max(1, int(payload["max_retries"]))
        self.settings_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_env_lines(self) -> list[str]:
        if not self.env_path.exists():
            return []
        return self.env_path.read_text(encoding="utf-8").splitlines()

    def get_api_key(self) -> str | None:
        for line in self._read_env_lines():
            if line.startswith(f"{API_KEY_NAME}="):
                value = line.split("=", 1)[1].strip()
                return value or None
        return None

    def set_api_key(self, key: str) -> None:
        lines = [
            line for line in self._read_env_lines()
            if not line.startswith(f"{API_KEY_NAME}=")
        ]
        lines.append(f"{API_KEY_NAME}={key.strip()}")
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def delete_api_key(self) -> None:
        lines = [
            line for line in self._read_env_lines()
            if not line.startswith(f"{API_KEY_NAME}=")
        ]
        if not self.env_path.exists() and not lines:
            return
        self.env_path.write_text(
            ("\n".join(lines) + "\n") if lines else "", encoding="utf-8"
        )

    def masked_api_key(self) -> str | None:
        key = self.get_api_key()
        if not key:
            return None
        return f"{key[:VISIBLE_PREFIX_LENGTH]}****"
