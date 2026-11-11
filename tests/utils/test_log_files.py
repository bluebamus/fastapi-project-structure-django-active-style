"""로그 파일 — 프로세스별 파일 이름, 날짜·크기 회전, 보관 일수, fork 뒤 큐 listener 재시작."""

import io
import logging
import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from config import LogSettings


def _build(monkeypatch, tmp_path, env="production", **log):
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in log.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


# =============================================================================
# L5. 파일 분할 — 프로세스별 + 에러
# =============================================================================
@pytest.mark.parametrize(
    ("process", "main", "error"),
    [("app", "app.log", "error.log"), ("celery", "celery.log", "celery-error.log")],
)
def test_file_names_follow_the_process_kind(monkeypatch, tmp_path, process, main, error):
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config, "_process", process)
    cfg = _build(monkeypatch, tmp_path, LOG_FILE_ENABLED=True)
    assert os.path.basename(cfg["handlers"]["file"]["filename"]) == main
    assert os.path.basename(cfg["handlers"]["error_file"]["filename"]) == error
    for name in ("file", "error_file"):
        handler = cfg["handlers"][name]
        assert handler["()"] == "app.utils.logs.handlers.DailyRotatingFileHandler"
        assert handler["retention_days"] == logs_config.log_settings.LOG_RETENTION_DAYS


def test_set_process_rejects_unknown_kind():
    from app.utils.logs import config as logs_config

    with pytest.raises(ValueError):
        logs_config.set_process("beat")


# =============================================================================
# L6. 회전 · 보관 — 날짜 + 크기 + 보관일수 (tmp 경로의 실제 파일)
# =============================================================================
def _handler(tmp_path, **kw):
    from app.utils.logs.handlers import DailyRotatingFileHandler

    handler = DailyRotatingFileHandler(str(tmp_path / "app.log"), **kw)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _emit(handler, msg):
    handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, msg, (), None))


def _day(days_ago=0):
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def test_midnight_rollover_renames_to_the_previous_day(tmp_path):
    handler = _handler(tmp_path)
    try:
        _emit(handler, "yesterday line")
        handler.rolloverAt = int(time.time()) - 1  # 자정이 지났다
        _emit(handler, "today line")
    finally:
        handler.close()
    rolled = tmp_path / f"app.log.{_day(1)}"
    assert rolled.read_text(encoding="utf-8").strip() == "yesterday line"
    assert (tmp_path / "app.log").read_text(encoding="utf-8").strip() == "today line"
    assert handler.rolloverAt > time.time()


def test_size_overflow_splits_within_the_day(tmp_path):
    handler = _handler(tmp_path, max_bytes=30)
    try:
        for i in range(4):
            _emit(handler, f"line-{i}-xxxxxxxxxxxxxxx")  # 줄마다 25바이트 남짓 — 줄마다 넘친다
    finally:
        handler.close()
    names = sorted(p.name for p in tmp_path.iterdir())
    today = _day()
    assert names == ["app.log", f"app.log.{today}", f"app.log.{today}.1", f"app.log.{today}.2"]
    assert (tmp_path / f"app.log.{today}").read_text(encoding="utf-8").startswith("line-0")
    assert (tmp_path / "app.log").read_text(encoding="utf-8").startswith("line-3")


def _seed(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("old\n", encoding="utf-8")


def test_retention_keeps_exactly_n_days_and_deletes_older_including_splits(tmp_path):
    _seed(
        tmp_path,
        f"app.log.{_day(7)}",
        f"app.log.{_day(7)}.1",
        f"app.log.{_day(8)}",
        f"app.log.{_day(8)}.3",
        f"app.log.{_day(30)}",
        "error.log.2000-01-01",  # 다른 파일의 이력은 건드리지 않는다
    )
    handler = _handler(tmp_path, retention_days=7)
    try:
        _emit(handler, "a")
        handler.rolloverAt = int(time.time()) - 1
        _emit(handler, "b")
    finally:
        handler.close()
    names = {p.name for p in tmp_path.iterdir()}
    assert f"app.log.{_day(7)}" in names and f"app.log.{_day(7)}.1" in names
    assert not {f"app.log.{_day(8)}", f"app.log.{_day(8)}.3", f"app.log.{_day(30)}"} & names
    assert "error.log.2000-01-01" in names


def test_retention_zero_deletes_nothing(tmp_path):
    _seed(tmp_path, "app.log.2000-01-01", "app.log.2000-01-01.1")
    handler = _handler(tmp_path, retention_days=0)
    try:
        _emit(handler, "a")
        handler.rolloverAt = int(time.time()) - 1
        _emit(handler, "b")
    finally:
        handler.close()
    names = {p.name for p in tmp_path.iterdir()}
    assert {"app.log.2000-01-01", "app.log.2000-01-01.1"} <= names


def test_negative_retention_is_a_settings_error():
    with pytest.raises(ValidationError, match="LOG_RETENTION_DAYS"):
        LogSettings(_env_file=None, LOG_RETENTION_DAYS=-1)


def test_warns_when_files_are_on_in_a_spawned_worker_process(monkeypatch, tmp_path, caplog):
    """uvicorn --workers 2 이상은 워커를 spawn 한다 — 같은 파일을 여러 프로세스가 회전시킨다."""
    import multiprocessing

    from app.utils.logs import config as logs_config
    from app.utils.logs import setup as logs_setup

    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
    monkeypatch.setattr(logs_setup, "start_queue_listener", lambda handler: False)
    for parent, warns in ((None, False), (object(), True)):
        monkeypatch.setattr(multiprocessing, "parent_process", lambda p=parent: p)
        monkeypatch.setattr(logs_setup, "_configured", False)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            logs_setup.configure_logging()
        found = [r for r in caplog.records if "여러 프로세스" in r.getMessage()]
        assert bool(found) is warns


def test_listener_is_restarted_after_fork(monkeypatch):
    """prefork 자식은 listener 스레드를 물려받지 못한다 — 같은 큐·핸들러로 다시 세운다."""
    import queue
    from logging.handlers import QueueListener

    from app.utils.logs import queue_logging

    io_buffer = io.StringIO()
    buf_handler = logging.StreamHandler(io_buffer)
    inherited = QueueListener(queue.Queue(), buf_handler)  # fork 로 복제된, 스레드 없는 listener
    saved = queue_logging._listener
    queue_logging._listener = inherited
    monkeypatch.setattr(queue_logging, "_listener_pid", -1)  # 부모 프로세스가 시작한 listener
    try:
        assert queue_logging.restart_queue_listener_after_fork() is True
        inherited.queue.put_nowait(logging.makeLogRecord({"msg": "from-child"}))
        queue_logging.stop_queue_listener_sync()
    finally:
        queue_logging._listener = saved
    assert "from-child" in io_buffer.getvalue()


def test_listener_is_not_restarted_in_the_same_process(monkeypatch):
    """solo 풀은 worker_process_init 을 **같은 프로세스**에서 보낸다 — 살아 있는 listener 옆에 둘째를 세우지 않는다."""
    import os
    import queue
    from logging.handlers import QueueListener

    from app.utils.logs import queue_logging

    live = QueueListener(queue.Queue(), logging.NullHandler())
    monkeypatch.setattr(queue_logging, "_listener", live)
    monkeypatch.setattr(queue_logging, "_listener_pid", os.getpid())
    assert queue_logging.restart_queue_listener_after_fork() is False
    assert queue_logging._listener is live


def test_worker_process_init_restarts_the_listener(monkeypatch):
    from app.celery import worker_lifecycle
    from app.core.db import session as session_module
    from app.utils.logs import queue_logging

    class _Engine:
        class sync_engine:  # noqa: N801
            @staticmethod
            def dispose(close=True):
                return None

    monkeypatch.setattr(session_module, "engine", _Engine, raising=False)
    monkeypatch.setattr(session_module, "background_engine", _Engine, raising=False)
    monkeypatch.setattr(session_module, "read_engines", [], raising=False)
    calls = []
    monkeypatch.setattr(queue_logging, "restart_queue_listener_after_fork", lambda: calls.append(1))
    worker_lifecycle.on_worker_process_init()
    assert calls == [1]


@pytest.mark.parametrize(
    "argv,kind",
    [
        (["/venv/bin/celery", "-A", "app.celery.app:celery_app", "worker"], "celery"),
        ([r"C:\venv\Scripts\celery.exe", "-A", "app.celery.app:celery_app", "beat"], "celery"),
        (["/venv/lib/python3.14/site-packages/celery/__main__.py", "-A", "x", "worker"], "celery"),
        (["/venv/bin/uvicorn", "main:app"], "app"),
        (["main.py"], "app"),
        (["-c"], "app"),
        ([], "app"),
    ],
)
def test_process_kind_comes_from_the_entrypoint(argv, kind):
    """Celery 신호를 기다리면 그 전 줄(설정 로드·라우팅 구성)이 웹 파일(app.log)로 간다."""
    from app.utils.logs import config as logs_config

    assert logs_config.process_from_argv(argv) == kind
