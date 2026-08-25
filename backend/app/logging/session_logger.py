"""生成セッション単位のログ。フロントへの SSE 配信とファイル保存を兼ねる。

不具合の原因追跡を目的とするため、どの Stage で何が起きたかを
必ず残す。イベントの追加はワーカースレッドから呼ばれるためロックで守る。
"""
import queue
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


@dataclass(frozen=True, slots=True)
class LogEvent:
    level: str
    message: str
    timestamp: str
    stage: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


MAX_LOG_FILES = 50
"""残しておくログファイルの数。古いものから消す。

不具合の原因を追うのに要るのは直近の数回で、それ以前は溜まるだけ。
実際 380 ファイル・1.2MB まで増えていた。
"""


def prune_logs(directory: Path, keep: int = MAX_LOG_FILES) -> None:
    """新しい順に keep 件を残し、それより古いものを消す。"""
    try:
        files = sorted(
            directory.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True
        )
    except OSError:
        return
    for stale in files[keep:]:
        try:
            stale.unlink()
        except OSError:
            pass  # 使用中などで消せなくても、ログを書く邪魔はしない


class SessionLogger:
    """1 回の生成に対応するロガー。"""

    def __init__(self, session_id: str, log_dir: Path | None = None) -> None:
        self.session_id = session_id
        directory = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        directory.mkdir(parents=True, exist_ok=True)
        prune_logs(directory)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.log_path = directory / f"{stamp}_{session_id}.log"

        self._events: list[LogEvent] = []
        self._subscribers: list[queue.SimpleQueue] = []
        self._lock = threading.Lock()
        self._closed = False
        # 1 行も書かないロガーはファイルを作らない。読み込みと復元は
        # 問題が無ければ何も書かず、空ファイルだけが残っていた。
        self._file = None

    @property
    def events(self) -> list[LogEvent]:
        with self._lock:
            return list(self._events)

    def subscribe(self) -> queue.SimpleQueue:
        """以降のイベントを受け取るキューを返す。close() で None が届く。

        既に閉じている場合は None を入れたキューを返す。生成が速く
        終わった直後に SSE が接続してきても、待ち続けずに済む。
        """
        stream: queue.SimpleQueue = queue.SimpleQueue()
        with self._lock:
            if self._closed:
                stream.put(None)
                return stream
            self._subscribers.append(stream)
        return stream

    def unsubscribe(self, stream) -> None:
        """購読をやめる。画面を閉じた購読者へ書き続けないため。"""
        with self._lock:
            if stream in self._subscribers:
                self._subscribers.remove(stream)

    def log(self, level: str, message: str, *, stage: str | None = None) -> None:
        """イベントを記録する。閉じた後の呼び出しは何もしない。

        ワーカーがエラー経路で遅れてイベントを出しても、例外で
        後始末を壊さないようにするため。
        """
        event = LogEvent(
            level=level,
            message=message,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            stage=stage,
        )
        with self._lock:
            if self._closed:
                return
            self._events.append(event)
            subscribers = list(self._subscribers)
            prefix = f"[{event.timestamp}] {level:<5}"
            suffix = f" ({stage})" if stage else ""
            if self._file is None:
                self._file = self.log_path.open("a", encoding="utf-8")
            self._file.write(f"{prefix} {message}{suffix}\n")
            self._file.flush()
        for stream in subscribers:
            stream.put(event)

    def info(self, message: str, *, stage: str | None = None) -> None:
        self.log("INFO", message, stage=stage)

    def warn(self, message: str, *, stage: str | None = None) -> None:
        self.log("WARN", message, stage=stage)

    def error(self, message: str, *, stage: str | None = None) -> None:
        self.log("ERROR", message, stage=stage)

    def close(self) -> None:
        """購読者に終了を伝え、ファイルを閉じる。二度呼んでも安全。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = list(self._subscribers)
            self._subscribers.clear()
            if self._file is not None and not self._file.closed:
                self._file.close()
        for stream in subscribers:
            stream.put(None)
