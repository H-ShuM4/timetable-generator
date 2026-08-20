"""API キーと生成設定の永続化。

API キーは .env、それ以外は data/settings.json に置く。
フロントへ返すのはマスク済みの文字列だけで、全文は返さない。
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

API_KEY_NAME = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_RETRIES = 3
VISIBLE_PREFIX_LENGTH = 6
"""マスク時に見せる先頭文字数の上限。"""

HIDDEN_MINIMUM = 4
"""マスク時に必ず隠す末尾文字数。短いキーで全文が露出するのを防ぐ。"""

_BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = _BACKEND_DIR / ".env"
DEFAULT_SETTINGS_PATH = _BACKEND_DIR / "data" / "settings.json"


@dataclass(slots=True)
class AppSettings:
    model: str = DEFAULT_MODEL
    max_retries: int = DEFAULT_MAX_RETRIES
    fallback_models: list[str] = field(default_factory=list)
    """model の枠が尽きたときに順に使う予備モデル。既定は空。

    開発時に無料枠を足し合わせるための機能である。空のときは model
    だけを使うため、事務局の運用では従来と完全に同じ挙動になる。
    """

    def models_in_order(self) -> list[str]:
        """実際に使う順に並べたモデル名。先頭が model。"""
        return [self.model, *self.fallback_models]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_fallback_models(value, model: str) -> list[str]:
    """予備モデルの一覧を整える。

    空文字・重複・model と同じ名前を落とす。model は必ず先頭で使われる
    ので、予備に重ねて入っていると同じモデルへ二度切り替えることになる。
    """
    if not isinstance(value, (list, tuple)):
        return []
    seen = {model.strip()}
    result: list[str] = []
    for item in value:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


class SettingsStore:
    def __init__(
        self, env_path: Path | None = None, settings_path: Path | None = None
    ) -> None:
        self.env_path = Path(env_path) if env_path else DEFAULT_ENV_PATH
        self.settings_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH

    def load(self) -> AppSettings:
        """settings.json を読み込む。壊れている場合はデフォルト値にフォールバックする。

        設定タブは API キー不正時の唯一の修正経路であるため、無関係な理由で
        500 を返してはならない。
        """
        if not self.settings_path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings.json の内容がオブジェクトではありません")
            model = raw.get("model", DEFAULT_MODEL) or DEFAULT_MODEL
            return AppSettings(
                model=model,
                max_retries=max(1, int(raw.get("max_retries", DEFAULT_MAX_RETRIES))),
                fallback_models=normalize_fallback_models(
                    raw.get("fallback_models", []), model
                ),
            )
        except (json.JSONDecodeError, ValueError, TypeError, OSError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.to_dict()
        payload["max_retries"] = max(1, int(payload["max_retries"]))
        payload["fallback_models"] = normalize_fallback_models(
            payload["fallback_models"], payload["model"]
        )
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
        """フロントへ返す表示用の文字列。全文は決して返さない。

        末尾 HIDDEN_MINIMUM 文字は必ず隠すため、短いキーを入れられても
        全文が露出しない。
        """
        key = self.get_api_key()
        if not key:
            return None
        visible = min(VISIBLE_PREFIX_LENGTH, max(0, len(key) - HIDDEN_MINIMUM))
        return f"{key[:visible]}****"
