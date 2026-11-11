"""로그 설정 — 콘솔·파일 포맷과 날짜 형식, 필수 필드 검증, 콘솔 끄기, 헤더별 레벨(`LOG_APP_LEVELS`),
실행 경로(python main.py·uvicorn·Celery)마다 같은 형식.
"""

import logging
import re
import sys
from logging.config import dictConfig

import pytest
from pydantic import ValidationError

from app.utils.logs import config as logs_config
from app.utils.logs import filters as logs_filters
from app.utils.logs import setup as logs_setup
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
        r"\[test_log_settings:-:_app_console_lines:\d+\] hello",
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


def test_uvicorn_lines_follow_console_and_date_format(monkeypatch, tmp_path):
    """`python main.py` 경로 — uvicorn 로거는 설정 없이 root(앱 콘솔 형식)로 전파된다.

    예전에는 접속 줄만 전용 형식을 썼다. 이제 접속 줄도 같은 형식이고 {message} 가 요청 줄이다.
    """
    _settings(
        monkeypatch,
        tmp_path,
        LOG_CONSOLE_FORMAT="U|{levelname}|{asctime}|{message}",
        LOG_DATE_FORMAT="%d/%m/%Y",
    )
    with _isolated_loggers(*UVICORN_LOGGERS):
        dictConfig(logs_config.build_dictconfig())
        buf = _capture(logging.getLogger())
        logging.getLogger("uvicorn.error").info("hello")
        # uvicorn 이 실제로 남기는 모양 그대로(args 5개).
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/", "1.1", 200
        )

    assert buf.getvalue().splitlines() == [
        line for line in buf.getvalue().splitlines() if line.startswith("U|INFO|")
    ]
    assert re.fullmatch(
        r"U\|INFO\|\d{2}/\d{2}/\d{4}\|hello\n"
        r'U\|INFO\|\d{2}/\d{2}/\d{4}\|1\.2\.3\.4:5 - "GET / HTTP/1\.1" 200\n',
        buf.getvalue(),
    ), buf.getvalue()


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

    app_log = tmp_path / "app.log"  # logging-overhaul L5 — 웹 프로세스 파일
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
def test_celery_task_logger_handlers_go_to_root(monkeypatch, tmp_path, enabled):
    """celery.task 의 자기 핸들러는 걷히고 root 로 전파된다 — 콘솔 on/off 는 root 의 콘솔 하나가 따른다."""
    from app.celery.worker_lifecycle import on_setup_logger

    monkeypatch.setattr(logs_config.log_settings, "LOG_CONSOLE_ENABLED", enabled, raising=False)
    with _isolated_loggers("celery-probe"):
        probe = logging.getLogger("celery-probe")
        console = logging.StreamHandler(sys.stderr)  # Celery 가 붙이는 콘솔 핸들러 자리
        file_handler = logging.FileHandler(tmp_path / "worker.log", delay=True)
        probe.handlers[:] = [console, file_handler]
        probe.propagate = False
        on_setup_logger(logger=probe)
        assert probe.handlers == [] and probe.propagate is True
        file_handler.close()
    assert ("console" in logs_config.build_dictconfig()["handlers"]) is enabled


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
        LOG_CONSOLE_FORMAT=(
            "{tzname} {asctime} {levelname} {appname} {module} {classname} {funcName} {name} {message}"
        ),
        LOG_FILE_FORMAT="{asctime}|{levelname:8}|{appname}|{module}.{classname}.{funcName}|{message}",
        LOG_DATE_FORMAT="%H:%M",
    )
    assert settings.LOG_DATE_FORMAT == "%H:%M"


SITE = "/opt/venv/lib/python3.14/site-packages"


# =============================================================================
# L3. 필수 필드 — 형식에 빠지면 설정 오류
# =============================================================================
REQUIRED = ("asctime", "levelname", "appname", "module", "classname", "funcName", "message")


@pytest.mark.parametrize("key", ["LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT"])
@pytest.mark.parametrize("missing", REQUIRED)
def test_format_missing_a_required_field_is_a_settings_error(key, missing):
    fmt = " ".join(f"{{{name}}}" for name in REQUIRED if name != missing)
    with pytest.raises(ValidationError, match=rf"{key}[\s\S]*{missing}"):
        LogSettings(_env_file=None, **{key: fmt})


def test_error_lists_every_missing_field():
    with pytest.raises(ValidationError) as info:
        LogSettings(_env_file=None, LOG_CONSOLE_FORMAT="{asctime} {message}")
    text = str(info.value)
    for name in ("levelname", "appname", "module", "classname", "funcName"):
        assert name in text


def test_default_formats_have_every_required_field():
    settings = LogSettings(_env_file=None)
    assert settings.LOG_CONSOLE_FORMAT and settings.LOG_FILE_FORMAT


# =============================================================================
# L4. 앱별 레벨 — LOG_APP_LEVELS
# =============================================================================
def test_app_levels_parse_and_validate():
    settings = LogSettings(_env_file=None, LOG_APP_LEVELS=" blog=debug , celery=INFO,,")
    assert settings.get_app_levels() == {"blog": "DEBUG", "celery": "INFO"}
    assert LogSettings(_env_file=None, LOG_APP_LEVELS="").get_app_levels() == {}


@pytest.mark.parametrize("value", ["blog=LOUD", "blog", "=INFO", "blog=INFO=x", "blog=10"])
def test_bad_app_levels_are_a_settings_error(value):
    with pytest.raises(ValidationError, match="LOG_APP_LEVELS"):
        LogSettings(_env_file=None, LOG_APP_LEVELS=value)


def _labeled(appname, level):
    record = logging.LogRecord("x", level, __file__, 1, "m", (), None)
    record.appname = appname
    return record


def test_app_level_filter_drops_records_below_the_header_level():
    from app.utils.logs.filters import AppLevelFilter

    f = AppLevelFilter(levels={"blog": "DEBUG", "sqlalchemy": "WARNING"}, default="INFO")
    assert f.filter(_labeled("blog", logging.DEBUG))
    assert not f.filter(_labeled("sqlalchemy", logging.INFO))
    assert f.filter(_labeled("sqlalchemy", logging.WARNING))
    assert not f.filter(_labeled("core", logging.DEBUG))  # 지정 없음 → LOG_LEVEL
    assert f.filter(_labeled("core", logging.INFO))


def _build(monkeypatch, tmp_path, env="production", **log):
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in log.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


def test_root_level_is_lowered_to_the_minimum_and_filter_is_on_every_handler(monkeypatch, tmp_path):
    cfg = _build(
        monkeypatch, tmp_path, LOG_LEVEL="INFO", LOG_APP_LEVELS="blog=DEBUG", LOG_FILE_ENABLED=True
    )
    assert cfg["root"]["level"] == "DEBUG"
    assert cfg["filters"]["app_levels"]["levels"] == {"blog": "DEBUG"}
    assert cfg["filters"]["app_levels"]["default"] == "INFO"
    for name in ("console", "queue"):
        filters = cfg["handlers"][name]["filters"]
        assert filters[:2] == ["context", "app_levels"], (name, filters)


def test_app_levels_end_to_end(monkeypatch, tmp_path):
    """blog=DEBUG 만 DEBUG 가 나오고, 다른 헤더는 LOG_LEVEL(INFO) 을 따른다."""
    from tests.utils.test_log_redaction import (
        _app_config_on_probe_logger,
        _capture,
        _isolated_loggers,
    )

    cfg = _build(
        monkeypatch,
        tmp_path,
        env="development",
        LOG_LEVEL="INFO",
        LOG_CONSOLE_LEVEL="DEBUG",
        LOG_APP_LEVELS="blog=DEBUG",
    )
    with _isolated_loggers("redaction-probe"):
        dictConfig(_app_config_on_probe_logger(cfg))
        probe = logging.getLogger("redaction-probe")
        buf = _capture(probe)
        probe.debug("app-debug")
        probe.debug("blog-debug", extra={"appname": "blog"})
        probe.info("app-info")
    text = buf.getvalue()
    assert "blog-debug" in text and "app-info" in text
    assert "app-debug" not in text


def test_unknown_app_level_header_only_warns(monkeypatch, caplog):
    from app.utils.logs import setup as logs_setup

    monkeypatch.setattr(logs_setup.log_settings, "LOG_APP_LEVELS", "blog=DEBUG,nosuchapp=INFO")
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
    monkeypatch.setattr(logs_setup, "_configured", False)
    monkeypatch.setattr(logs_setup, "start_queue_listener", lambda handler: False)
    with caplog.at_level(logging.WARNING):
        logs_setup.configure_logging()
    warned = [r.getMessage() for r in caplog.records if "LOG_APP_LEVELS" in r.getMessage()]
    assert len(warned) == 1, warned
    assert "nosuchapp" in warned[0] and "'blog'" not in warned[0]


# =============================================================================
# L1. 포맷 통일 — 앱 · python main.py · uvicorn main:app · Celery(메인+태스크), 콘솔·파일 모두
#
# 각 경로를 실제 순서대로 재현한다: 외부 도구가 먼저 자기 핸들러를 세우고(uvicorn LOGGING_CONFIG,
# Celery 의 root·celery.task 핸들러), 그다음 우리 구성이 적용된다. 출력은 root 콘솔(버퍼)과 실제
# 파일(tmp)에서 읽는다. 비밀값 원문이 어느 출력에도 없는지 같은 실행에서 본다.
# =============================================================================
LINE = re.compile(
    r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})? \S+\] (?P<level>[A-Z]+) +"
    r"\[app=(?P<app>[^\]]+)\] \[(?P<module>[^:\]]+):(?P<cls>[^:\]]+):(?P<func>[^:\]]+):\d+\] "
    r"(?P<msg>.*)"
)


SITE_UVICORN = f"{SITE}/uvicorn/protocols/http/h11_impl.py"


SITE_CELERY = f"{SITE}/celery/worker/strategy.py"


DB_PASSWORD = "Db-Pass-Sentinel-91"


DB_USER = "dbuser_sentinel"


JWT_KEY = "jwt-access-key-sentinel-0123456789"


EXTERNAL = ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task")


def _external(logger_name, pathname, msg, args=(), func="send"):
    record = logging.LogRecord(logger_name, logging.INFO, pathname, 7, msg, args, None, func)
    logging.getLogger(logger_name).handle(record)


def _lines(text):
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        assert LINE.fullmatch(line), f"프로젝트 형식이 아닌 줄: {line!r}"
    return {LINE.fullmatch(line)["msg"]: LINE.fullmatch(line) for line in lines}


@pytest.fixture
def project_logging(monkeypatch, tmp_path):
    """실제 configure_logging() 을 root 에 적용하고(파일 켬, tmp LOG_DIR) 끝나면 모두 되돌린다."""
    import config
    from app.utils.logs import config as logs_config
    from app.utils.logs import queue_logging
    from app.utils.logs import setup as logs_setup
    from tests.utils.test_log_redaction import _isolated_loggers

    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_LEVEL", "INFO", raising=False)
    monkeypatch.setattr(logs_config, "_process", "app")
    monkeypatch.setattr(logs_setup, "_configured", False)
    monkeypatch.setattr(config.db_settings, "MYSQL_PASSWORD", DB_PASSWORD)
    monkeypatch.setattr(config.db_settings, "MYSQL_USER", DB_USER)
    monkeypatch.setattr(config.jwt_settings, "ACCESS_TOKEN_SECRET_KEY", JWT_KEY)
    with _isolated_loggers(*EXTERNAL):
        try:
            yield tmp_path
        finally:
            queue_logging.stop_queue_listener_sync()
            logs_filters.set_secret_values([])


def _console(buf):
    from tests.utils.test_log_redaction import _capture

    return _capture(logging.getLogger()) if buf is None else buf


def _assert_no_secret(*texts):
    for text in texts:
        for secret in (DB_PASSWORD, DB_USER, JWT_KEY):
            assert secret not in text, f"비밀값 원문이 남았다: {secret}"


def test_web_paths_share_one_format_on_console_and_file(project_logging):
    """앱 로거 · python main.py(uvicorn 설정 없음) · uvicorn main:app(CLI 기본 핸들러)."""
    import uvicorn.config

    from app.utils.logs import get_logger
    from app.utils.logs import setup as logs_setup

    dictConfig(uvicorn.config.LOGGING_CONFIG)  # uvicorn CLI 가 앱 import 전에 하는 일
    logs_setup.configure_logging()
    buf = _console(None)

    get_logger("probe").info("app line user=%s pw=%s", DB_USER, DB_PASSWORD)
    _external(
        "uvicorn.access",
        SITE_UVICORN,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", f"/p?k={JWT_KEY}", "1.1", 200),
    )
    _external("uvicorn.error", SITE_UVICORN, "Started server process")
    logs_setup.configure_logging(force=True)  # listener 를 멈춰 파일을 flush 한다(재구성 경로)

    console = buf.getvalue()
    app_log = (project_logging / "app.log").read_text(encoding="utf-8")
    _assert_no_secret(console, app_log)
    for text in (console, app_log):
        lines = _lines(text)
        app_line = next(m for msg, m in lines.items() if msg.startswith("app line"))
        assert (app_line["app"], app_line["module"]) == ("app", "test_log_settings")
        access = next(m for msg, m in lines.items() if msg.startswith("1.2.3.4:5"))
        assert access["app"] == "uvicorn"
        assert access["msg"] == '1.2.3.4:5 - "GET /p?k=*** HTTP/1.1" 200'
        assert lines["Started server process"]["app"] == "uvicorn"
    # CLI 기본 핸들러가 남아 같은 줄을 두 번 찍지 않는다.
    assert console.count("Started server process") == 1
    for name in ("uvicorn", "uvicorn.access"):
        assert logging.getLogger(name).handlers == [] and logging.getLogger(name).propagate


def test_celery_worker_and_task_lines_share_the_format(project_logging):
    """Celery 워커 — root 를 가로챈 핸들러·--logfile·celery.task 핸들러를 거쳐도 같은 형식·헤더."""
    from app.celery.worker_lifecycle import on_setup_logger
    from app.utils.logs import config as logs_config
    from app.utils.logs import setup as logs_setup

    logs_setup.configure_logging()  # 워커도 app.celery.app import 때 한 번 구성된다
    root = logging.getLogger()
    logfile = project_logging / "worker.log"
    # Celery 가 하는 일: root 핸들러를 비우고 자기 핸들러(콘솔 또는 --logfile)를 단다.
    root.handlers[:] = [logging.StreamHandler(sys.stderr)]
    task_logger = logging.getLogger("celery.task")
    task_logger.handlers[:] = [logging.StreamHandler(sys.stderr)]
    task_logger.propagate = False
    on_setup_logger(logger=root, logfile=str(logfile))
    on_setup_logger(logger=task_logger, logfile=str(logfile))
    buf = _console(None)

    assert logs_config._process == "celery"
    _external(
        "app.features.home.tasks",
        "/x/app/features/home/tasks.py",
        f"task ran secret={DB_PASSWORD}",
        func="cleanup",
    )
    _external("celery.worker.strategy", SITE_CELERY, "Task received")
    logs_setup.configure_logging(force=True)  # flush

    console = buf.getvalue()
    worker_log = logfile.read_text(encoding="utf-8")
    celery_log = (project_logging / "celery.log").read_text(encoding="utf-8")
    _assert_no_secret(console, worker_log, celery_log)
    for text in (console, worker_log, celery_log):
        lines = _lines(text)
        assert lines["Task received"]["app"] == "celery"
        task = next(m for msg, m in lines.items() if msg.startswith("task ran"))
        assert (task["app"], task["func"]) == ("home", "cleanup")
        assert console.count("Task received") == 1
    assert not (project_logging / "app.log").exists() or "Task received" not in (
        project_logging / "app.log"
    ).read_text(encoding="utf-8")


def test_python_main_passes_no_uvicorn_log_config():
    """`python main.py` 는 uvicorn 에 자기 형식을 주지 않는다 — uvicorn 로거는 root(프로젝트 형식)로 간다."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    run = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "run"
    )
    log_config = next(k.value for k in run.keywords if k.arg == "log_config")
    assert isinstance(log_config, ast.Constant) and log_config.value is None
