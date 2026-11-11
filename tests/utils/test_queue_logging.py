"""파일 로깅을 event loop 밖으로 밀어내는 queue 계약.

여기서 확인하는 것은 "로그가 남는가" 가 아니라 **어디서 파일 쓰기가 일어나는가** 다.
`RotatingFileHandler` 가 root 에 직접 붙어 있으면 로그를 남기는 코루틴이 파일 쓰기와
로테이션을 직접 수행해 event loop 가 그만큼 멈춘다. 그 구조는 정상 동작 테스트로는
절대 드러나지 않는다 — 로그는 어느 쪽이든 잘 남기 때문이다. 그래서 **구조**를 단언한다.
"""

import logging
import queue
from logging.config import dictConfig

from app.utils.logs import config as logs_config
from app.utils.logs.queue_logging import (
    LOG_QUEUE_MAXSIZE,
    BoundedQueueHandler,
    make_log_queue,
    start_queue_listener,
    stop_queue_listener,
)


def _build_production(monkeypatch, tmp_path) -> dict:
    """production 구성을 만든다. 로그 디렉터리는 tmp 로 — get_log_dir() 이 mkdir 을 한다."""
    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    return logs_config.build_dictconfig()


# ------------------------------------------------------------------ 큐 배치


def test_file_handlers_are_behind_a_queue(monkeypatch, tmp_path):
    """파일 핸들러가 root 에 직접 붙으면 파일 I/O 가 event loop 를 막는다."""
    cfg = _build_production(monkeypatch, tmp_path)

    assert "file" not in cfg["root"]["handlers"], "파일 핸들러가 root 에 직접 붙었습니다."
    assert "error_file" not in cfg["root"]["handlers"]
    assert "queue" in cfg["root"]["handlers"]
    assert set(cfg["handlers"]["queue"]["handlers"]) == {"file", "error_file"}


def test_queue_is_bounded(monkeypatch, tmp_path):
    """무한 큐는 블로킹을 메모리 증가로 바꿀 뿐이다."""
    cfg = _build_production(monkeypatch, tmp_path)

    assert cfg["handlers"]["queue"]["queue"] == {
        "()": "app.utils.logs.queue_logging.make_log_queue"
    }
    assert make_log_queue().maxsize == LOG_QUEUE_MAXSIZE
    assert LOG_QUEUE_MAXSIZE > 0


def test_noise_filter_sits_in_front_of_the_queue(monkeypatch, tmp_path):
    """버릴 레코드가 큐 자리를 차지하면 정작 필요한 로그가 상한에 걸려 드롭된다."""
    cfg = _build_production(monkeypatch, tmp_path)

    assert "sql_noise" in cfg["handlers"]["queue"]["filters"]


def test_development_has_no_queue(monkeypatch, tmp_path):
    """파일 로깅이 없으면 큐도 없다 — 쓰지 않는 스레드를 띄우지 않는다."""
    monkeypatch.setattr(logs_config.app_settings, "ENV", "development", raising=False)
    cfg = logs_config.build_dictconfig()

    assert "queue" not in cfg["handlers"]
    assert cfg["root"]["handlers"] == ["console"]


def test_dropped_records_are_counted_not_raised():
    """큐가 가득 차면 stderr 에 트레이스백을 쏟지 않고 조용히 세고 넘어간다."""
    handler = BoundedQueueHandler(queue.Queue(maxsize=1))
    before = BoundedQueueHandler.dropped
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)

    handler.enqueue(record)  # 큐를 채운다
    handler.enqueue(record)  # 넘친다 — 예외가 나면 이 테스트가 실패한다

    assert BoundedQueueHandler.dropped == before + 1


# ------------------------------------------------------------------ 드롭·listener


def test_listener_start_is_idempotent(monkeypatch, tmp_path):
    """두 진입점(`python main.py` / `uvicorn main:app`)에서 bootstrap 이 한 번만 일어난다."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "sink": {"class": "logging.NullHandler"},
                "queue": {
                    "class": "app.utils.logs.queue_logging.BoundedQueueHandler",
                    "queue": {"()": "app.utils.logs.queue_logging.make_log_queue"},
                    "handlers": ["sink"],
                },
            },
            "root": {"handlers": ["queue"], "level": "INFO"},
        }
    )
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, BoundedQueueHandler)

    try:
        assert start_queue_listener(handler) is True, "첫 호출이 listener 를 시작해야 합니다."
        assert start_queue_listener(handler) is False, "두 번째 호출이 또 시작했습니다."
    finally:
        import asyncio

        asyncio.run(stop_queue_listener())
        logging.getLogger().handlers.clear()


def test_start_is_noop_without_a_queue_handler():
    """큐가 구성되지 않은 환경(development/test)에서는 아무 일도 하지 않는다."""
    assert start_queue_listener(None) is False


async def test_stop_is_idempotent():
    await stop_queue_listener()
    await stop_queue_listener()  # 예외가 나면 실패
