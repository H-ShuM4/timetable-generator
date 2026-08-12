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
