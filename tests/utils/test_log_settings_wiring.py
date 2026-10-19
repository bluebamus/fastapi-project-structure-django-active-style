"""로그 설정(LOG_CONSOLE_FORMAT·LOG_FILE_FORMAT·LOG_DATE_FORMAT·LOG_CONSOLE_ENABLED) 연결 (config-cleanup-2).

설정을 바꾸면 **실제로 찍히는 줄**이 바뀌는지 본다 — dict 모양만 보면 포매터에 값이 들어가도
출력이 안 바뀌는 연결 실수를 놓친다. 출력 경로마다(앱 root·`python main.py` 의 uvicorn·
`uvicorn main:app` CLI·Celery 워커) 따로 확인한다.
"""

import logging
import re
import sys
from logging.config import dictConfig

import pytest
from pydantic import ValidationError

from app.utils.logs import config as logs_config
from app.utils.logs import setup as logs_setup
from app.utils.logs import setup_uvicorn_logging
from app.utils.logs.queue_logging import BoundedQueueHandler
from config import LogSettings
from tests.utils.test_log_redaction import _app_config_on_probe_logger, _capture, _isolated_loggers

# 연결 전 build_dictconfig 에 하드코딩돼 있던 형식 — 기본값이 이것과 같아야 기본 출력이 그대로다.
PREVIOUS_FORMAT = (
    "[{asctime} {tzname}] {levelname:5} [app={appname}] "
    "[{module}:{classname}:{funcName}:{lineno}] {message}"
)
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _settings(monkeypatch, tmp_path, env="production", **log):
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    log.setdefault("LOG_FILE_ENABLED", False)
    for key, value in log.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)


def _app_console_lines(monkeypatch, tmp_path, **kw) -> list[str]:
    _settings(monkeypatch, tmp_path, **kw)
    with _isolated_loggers("redaction-probe"):
        dictConfig(_app_config_on_probe_logger(logs_config.build_dictconfig()))
        probe = logging.getLogger("redaction-probe")
        buf = _capture(probe)
        probe.info("hello")
    return buf.getvalue().splitlines()


# =============================================================================
# 기본값 = 변경 전 출력
# =============================================================================
def test_format_defaults_equal_previous_hardcoded_values():
    fields = LogSettings.model_fields
    assert fields["LOG_CONSOLE_FORMAT"].default == PREVIOUS_FORMAT
    assert fields["LOG_FILE_FORMAT"].default == PREVIOUS_FORMAT
    assert fields["LOG_DATE_FORMAT"].default == "%Y-%m-%d %H:%M:%S"
    assert fields["LOG_CONSOLE_ENABLED"].default is True


def test_default_settings_keep_previous_console_line(monkeypatch, tmp_path):
    """development 기본: `[YYYY-MM-DD HH:MM:SS.mmm TZ] INFO  [app=..] [module:-:func:line] msg`."""
    lines = _app_console_lines(
        monkeypatch,
        tmp_path,
        env="development",
        LOG_CONSOLE_FORMAT=PREVIOUS_FORMAT,
        LOG_DATE_FORMAT="%Y-%m-%d %H:%M:%S",
    )
    assert len(lines) == 1, lines
    assert re.fullmatch(
        r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \S+\] INFO  \[app=[^\]]+\] "
        r"\[test_log_settings_wiring:-:_app_console_lines:\d+\] hello",
        lines[0],
    ), lines[0]


# =============================================================================
# 포맷·날짜 형식이 실제 출력 줄을 바꾼다
# =============================================================================
def test_console_format_and_date_format_shape_app_output(monkeypatch, tmp_path):
    lines = _app_console_lines(
        monkeypatch,
        tmp_path,
        LOG_CONSOLE_FORMAT="C|{levelname}|{asctime}|{message}",
        LOG_DATE_FORMAT="%d/%m/%Y",
    )
    assert len(lines) == 1, lines
    assert re.fullmatch(r"C\|INFO\|\d{2}/\d{2}/\d{4}\|hello", lines[0]), lines[0]


def test_development_appends_milliseconds_after_date_format(monkeypatch, tmp_path):
    lines = _app_console_lines(
        monkeypatch,
        tmp_path,
        env="development",
        LOG_CONSOLE_FORMAT="{asctime}|{message}",
        LOG_DATE_FORMAT="%H:%M:%S",
    )
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.\d{3}\|hello", lines[0]), lines


def test_uvicorn_log_config_follows_console_and_date_format(monkeypatch, tmp_path):
    """`python main.py` 경로 — setup_uvicorn_logging() 의 핸들러."""
    _settings(
        monkeypatch,
        tmp_path,
        LOG_CONSOLE_FORMAT="U|{levelname}|{asctime}|{message}",
        LOG_DATE_FORMAT="%d/%m/%Y",
    )
    with _isolated_loggers(*UVICORN_LOGGERS):
        dictConfig(setup_uvicorn_logging())
        error_logger = logging.getLogger("uvicorn.error")
        buf = _capture(error_logger)
        error_logger.info("hello")
        access_logger = logging.getLogger("uvicorn.access")
        access_buf = _capture(access_logger)
        access_logger.info(
            "x",
            extra={
                "client_addr": "1.2.3.4:5",
                "request_line": "GET / HTTP/1.1",
                "status_code": 200,
            },
        )

    assert re.fullmatch(
        r"U\|INFO\|\d{2}/\d{2}/\d{4}\|hello", buf.getvalue().strip()
    ), buf.getvalue()
    # access 줄은 요청 라인 전용 형식을 유지하되 날짜 형식은 따른다.
    assert re.match(
        r"\[\d{2}/\d{2}/\d{4} UTC\] INFO ", access_buf.getvalue()
    ), access_buf.getvalue()


def test_file_format_shapes_file_lines(monkeypatch, tmp_path):
    _settings(
        monkeypatch,
        tmp_path,
        LOG_FILE_ENABLED=True,
        LOG_FILE_FORMAT="F|{levelname}|{asctime}|{message}",
        LOG_DATE_FORMAT="%d/%m/%Y",
    )
    with _isolated_loggers("redaction-probe"):
        dictConfig(_app_config_on_probe_logger(logs_config.build_dictconfig()))
        probe = logging.getLogger("redaction-probe")
        buf = _capture(probe)
        listener = next(h for h in probe.handlers if isinstance(h, BoundedQueueHandler)).listener
        listener.start()
        try:
            probe.info("hello")
        finally:
            listener.stop()
            for handler in listener.handlers:
                handler.close()

    app_log = next(p for p in tmp_path.iterdir() if p.name.endswith("_app.log"))
    assert re.fullmatch(
        r"F\|INFO\|\d{2}/\d{2}/\d{4}\|hello", app_log.read_text(encoding="utf-8").strip()
    )
    # 콘솔은 콘솔 형식(기본)을 쓴다 — 파일 형식이 새지 않는다.
    assert not buf.getvalue().startswith("F|"), buf.getvalue()


# =============================================================================
# LOG_CONSOLE_ENABLED=false — 모든 경로에서 콘솔 핸들러가 빠진다
# =============================================================================
def _is_console(handler: logging.Handler) -> bool:
    return isinstance(handler, logging.StreamHandler) and not isinstance(
        handler, logging.FileHandler
    )


def test_console_disabled_drops_app_console_handler_keeps_file(monkeypatch, tmp_path):
    _settings(monkeypatch, tmp_path, LOG_FILE_ENABLED=True, LOG_CONSOLE_ENABLED=False)
    cfg = logs_config.build_dictconfig()
    assert "console" not in cfg["handlers"]
    assert cfg["root"]["handlers"] == ["queue"]
    assert set(cfg["handlers"]) == {"file", "error_file", "queue"}

    _settings(monkeypatch, tmp_path, env="development", LOG_CONSOLE_ENABLED=False)
    assert logs_config.build_dictconfig()["root"]["handlers"] == []


def test_console_disabled_drops_uvicorn_log_config_handlers(monkeypatch, tmp_path):
    """콘솔이 꺼지면 uvicorn 로거는 핸들러 없이 root(파일)로 전파한다 — 중복 없이 파일에만 남는다."""
    _settings(monkeypatch, tmp_path, LOG_CONSOLE_ENABLED=False)
    cfg = setup_uvicorn_logging()
    assert cfg["handlers"] == {}
    for name in UVICORN_LOGGERS:
        assert cfg["loggers"][name]["handlers"] == []
        assert cfg["loggers"][name]["propagate"] is True


def test_console_disabled_strips_uvicorn_cli_default_handlers(monkeypatch, tmp_path):
    """`uvicorn main:app` 경로 — uvicorn 이 앱 import 전에 세운 콘솔 핸들러를 걷어낸다."""
    import uvicorn.config

    _settings(monkeypatch, tmp_path, LOG_CONSOLE_ENABLED=False)
    with _isolated_loggers(*UVICORN_LOGGERS):
        dictConfig(uvicorn.config.LOGGING_CONFIG)
        assert any(_is_console(h) for n in UVICORN_LOGGERS for h in logging.getLogger(n).handlers)
        monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
        monkeypatch.setattr(logs_setup, "_configured", False)
        logs_setup.configure_logging()
        for name in UVICORN_LOGGERS:
            logger = logging.getLogger(name)
            assert not any(_is_console(h) for h in logger.handlers), name
            assert logger.handlers or logger.propagate, f"{name} 출력이 사라졌다"


@pytest.mark.parametrize("enabled", [True, False])
def test_celery_worker_console_handler_follows_setting(monkeypatch, tmp_path, enabled):
    from app.celery.worker_lifecycle import on_setup_logger

    monkeypatch.setattr(logs_config.log_settings, "LOG_CONSOLE_ENABLED", enabled, raising=False)
    with _isolated_loggers("celery-probe"):
        probe = logging.getLogger("celery-probe")
        console = logging.StreamHandler(sys.stderr)  # Celery 가 붙이는 콘솔 핸들러 자리
        file_handler = logging.FileHandler(tmp_path / "worker.log", delay=True)
        probe.handlers[:] = [console, file_handler]
        on_setup_logger(logger=probe)
        expected = [console, file_handler] if enabled else [file_handler]
        assert probe.handlers == expected


# =============================================================================
# 출력이 모두 꺼지면 시작 시 stderr 경고 한 줄
# =============================================================================
@pytest.mark.parametrize(
    ("env", "console", "file", "warns"),
    [
        ("development", False, True, True),  # development 는 파일 핸들러가 없다
        ("production", False, False, True),
        ("production", False, True, False),
        ("development", True, False, False),
    ],
)
def test_warns_once_when_every_output_is_off(
    monkeypatch, tmp_path, capsys, env, console, file, warns
):
    _settings(monkeypatch, tmp_path, env=env, LOG_CONSOLE_ENABLED=console, LOG_FILE_ENABLED=file)
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
    monkeypatch.setattr(logs_setup, "_configured", False)
    monkeypatch.setattr(logs_setup, "start_queue_listener", lambda handler: False)
    logs_setup.configure_logging()
    logs_setup.configure_logging()  # 멱등 — 두 번째 호출은 경고하지 않는다

    err = capsys.readouterr().err.splitlines()
    if warns:
        assert len(err) == 1 and "LOG_CONSOLE_ENABLED" in err[0], err
    else:
        assert err == []


# =============================================================================
# 설정 검증 — 잘못된 형식은 기동 시 오류
# =============================================================================
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("LOG_CONSOLE_FORMAT", "{foo} {message}"),  # 모르는 필드
        ("LOG_CONSOLE_FORMAT", "{asctime {message}"),  # 괄호 불일치
        ("LOG_FILE_FORMAT", "{levelname"),
        ("LOG_FILE_FORMAT", "{lineno:Z}"),  # 잘못된 형식 지정자
        ("LOG_DATE_FORMAT", ""),
        ("LOG_DATE_FORMAT", "   "),
    ],
)
def test_invalid_log_format_is_a_settings_error(key, value):
    with pytest.raises(ValidationError, match=key):
        LogSettings(_env_file=None, **{key: value})


def test_custom_format_using_project_fields_is_accepted():
    settings = LogSettings(
        _env_file=None,
        LOG_CONSOLE_FORMAT="{tzname} {appname} {classname} {name} {message}",
        LOG_FILE_FORMAT="{levelname:8} {message}",
        LOG_DATE_FORMAT="%H:%M",
    )
    assert settings.LOG_DATE_FORMAT == "%H:%M"
