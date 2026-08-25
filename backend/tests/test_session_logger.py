import json

from app.logging.session_logger import LogEvent, SessionLogger


def test_records_events_in_order(tmp_path):
    logger = SessionLogger("s1", log_dir=tmp_path)
    logger.info("開始", stage="Stage 0")
    logger.warn("教員が見つかりません")
    logger.error("API キーが無効です")

    assert [e.level for e in logger.events] == ["INFO", "WARN", "ERROR"]
    assert logger.events[0].stage == "Stage 0"
    assert logger.events[1].stage is None
    logger.close()


def test_writes_to_file(tmp_path):
    logger = SessionLogger("s2", log_dir=tmp_path)
    logger.info("テスト行")
    logger.close()

    assert logger.log_path.exists()
    content = logger.log_path.read_text(encoding="utf-8")
    assert "テスト行" in content
    assert "INFO" in content


def test_subscriber_receives_later_events(tmp_path):
    logger = SessionLogger("s3", log_dir=tmp_path)
    logger.info("購読前")
    stream = logger.subscribe()
    logger.info("購読後")

    received = stream.get(timeout=1)
    assert received.message == "購読後"
    logger.close()


def test_close_sends_sentinel_to_subscribers(tmp_path):
    logger = SessionLogger("s4", log_dir=tmp_path)
    stream = logger.subscribe()
    logger.close()
    assert stream.get(timeout=1) is None


def test_event_to_dict_is_json_serializable(tmp_path):
    logger = SessionLogger("s5", log_dir=tmp_path)
    logger.info("メッセージ", stage="Stage 2")
    payload = logger.events[0].to_dict()
    assert json.loads(json.dumps(payload))["message"] == "メッセージ"
    assert set(payload) == {"level", "message", "timestamp", "stage"}
    logger.close()


def test_timestamp_is_iso_format(tmp_path):
    from datetime import datetime

    logger = SessionLogger("s6", log_dir=tmp_path)
    logger.info("x")
    datetime.fromisoformat(logger.events[0].timestamp)
    logger.close()


def test_subscribing_after_close_receives_the_sentinel_immediately(tmp_path):
    # 生成が速く終わった直後に SSE が接続してくる場面。待たせてはいけない
    logger = SessionLogger("s7", log_dir=tmp_path)
    logger.info("開始")
    logger.close()

    stream = logger.subscribe()
    assert stream.get(timeout=1) is None


def test_logging_after_close_is_ignored(tmp_path):
    # ワーカーがエラー経路で遅れてイベントを出しても例外にしない
    logger = SessionLogger("s8", log_dir=tmp_path)
    logger.info("開始")
    logger.close()

    logger.error("後始末中のエラー")  # 例外を投げないこと
    assert [e.message for e in logger.events] == ["開始"]


def test_close_is_idempotent(tmp_path):
    logger = SessionLogger("s9", log_dir=tmp_path)
    stream = logger.subscribe()
    logger.close()
    logger.close()

    assert stream.get(timeout=1) is None
    assert stream.empty()


def test_a_logger_that_writes_nothing_leaves_no_file(tmp_path):
    """読み込みと復元は問題が無ければ何も書かない。空ファイルを残さない。"""
    logger = SessionLogger("quiet", log_dir=tmp_path)
    logger.close()
    assert list(tmp_path.glob("*.log")) == []


def test_the_file_appears_once_something_is_written(tmp_path):
    logger = SessionLogger("noisy", log_dir=tmp_path)
    logger.info("何かあった")
    logger.close()
    assert logger.log_path.exists()
    assert "何かあった" in logger.log_path.read_text(encoding="utf-8")


def test_old_logs_are_deleted(tmp_path):
    """溜まり続けないこと。実際 380 ファイルまで増えていた。"""
    import os
    import time

    from app.logging.session_logger import MAX_LOG_FILES

    for index in range(MAX_LOG_FILES + 12):
        path = tmp_path / f"old_{index:03d}.log"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (time.time() - (100 - index), time.time() - (100 - index)))

    logger = SessionLogger("new", log_dir=tmp_path)
    logger.info("記録")
    logger.close()

    remaining = sorted(p.name for p in tmp_path.glob("*.log"))
    assert len(remaining) == MAX_LOG_FILES + 1  # 残した分と、いま書いた分
    assert "old_000.log" not in remaining  # 最も古いものは消えている
    assert logger.log_path.name in remaining


def test_pruning_keeps_the_newest(tmp_path):
    import os
    import time

    from app.logging.session_logger import prune_logs

    for index in range(5):
        path = tmp_path / f"log_{index}.log"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (time.time() - (10 - index), time.time() - (10 - index)))

    prune_logs(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.glob("*.log")) == ["log_3.log", "log_4.log"]
