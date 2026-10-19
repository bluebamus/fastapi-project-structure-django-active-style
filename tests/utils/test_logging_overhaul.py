"""로깅 개편 (logging-overhaul) — 헤더·필수 필드·비밀값·앱별 레벨·파일 회전·보관.

각 테스트는 실제 레코드·실제 파일로 확인한다. 회전·보관 테스트는 tmp 경로에서 실제 파일을 만든다.
"""

import io
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from logging.config import dictConfig

import pytest
from pydantic import ValidationError

from app.utils.logs import filters as logs_filters
from app.utils.logs.filters import ContextFilter, RedactingFilter, _app_from_path, redact
from config import LogSettings

SITE = "/opt/venv/lib/python3.14/site-packages"


# =============================================================================
# L2. 헤더 — 외부 라이브러리는 로거 이름으로 출처를 붙인다
# =============================================================================
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("celery.worker.consumer", "celery"),
        ("celery", "celery"),
        ("kombu.connection", "celery"),
        ("uvicorn.access", "uvicorn"),
        ("uvicorn.error", "uvicorn"),
        ("sqlalchemy.engine.Engine", "sqlalchemy"),
        ("alembic.runtime.migration", "alembic"),
        ("httpx", "ext"),
        ("celeryx", "ext"),  # 접두사가 아니라 이름 단위로 맞춘다
    ],
)
def test_external_code_is_labeled_by_logger_name(name, expected):
    assert _app_from_path(f"{SITE}/pkg/mod.py", name) == expected


def test_our_code_keeps_path_rules_regardless_of_logger_name():
    assert _app_from_path("/x/app/features/blog/services.py", "celery") == "blog"
    assert _app_from_path("/x/app/celery/worker_lifecycle.py", "uvicorn") == "celery"


def test_context_filter_uses_logger_name_for_external_records():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, f"{SITE}/uvicorn/h.py", 1, "x", (), None
    )
    ContextFilter().filter(record)
    assert record.appname == "uvicorn"


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
# L7. 주요 정보 차단 — DSN 의 id·비밀번호, 설정된 비밀값 원문
# =============================================================================
@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("mysql+aiomysql://appuser:pw-123@db:3306/shop", "mysql+aiomysql://***:***@db:3306/shop"),
        ("redis://:redispw@cache:6379/0", "redis://***:***@cache:6379/0"),
    ],
)
def test_dsn_masks_both_user_and_password(dsn, expected):
    assert redact(f"connect {dsn}") == f"connect {expected}"


@pytest.fixture
def secrets():
    """설정 비밀값을 주입했다가 되돌린다."""
    yield logs_filters.set_secret_values
    logs_filters.set_secret_values([])


def test_configured_secret_values_are_masked_anywhere(secrets):
    secrets(["Sup3r-Secret-Value", "dbadmin"])
    out = redact("token Sup3r-Secret-Value in path /x/Sup3r-Secret-Value and owner dbadmin")
    assert "Sup3r-Secret-Value" not in out and "dbadmin" not in out
    assert out.count("***") == 3


def test_short_secret_masked_only_in_user_forms(secrets):
    """4글자 미만 값은 원문 일치로 가리지 않는다 — `user=`·`username=`·DSN 에서만."""
    secrets(["sa"])
    assert redact("usage salt sa") == "usage salt sa"
    assert redact("login user=sa ok") == "login user=*** ok"
    assert redact("username: 'sa'") == "username: '***'"
    assert redact("mysql://sa:pw@h/db") == "mysql://***:***@h/db"


def test_empty_secret_values_are_ignored(secrets):
    secrets(["", None, "   "])
    assert redact("plain text") == "plain text"


def test_secret_inside_exception_chain_is_masked(secrets):
    secrets(["chain-secret-777"])
    try:
        try:
            raise ConnectionError("inner chain-secret-777")
        except ConnectionError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError:
        record = logging.LogRecord("p", logging.ERROR, __file__, 1, "x", (), sys.exc_info())
    RedactingFilter().filter(record)
    out = logging.Formatter().format(record)
    assert "chain-secret-777" not in out and "direct cause" in out


def test_secret_in_access_line_arg_keeps_args_shape(secrets):
    secrets(["argsecret-42"])
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/x?k=argsecret-42", "1.1", 200),
        None,
    )
    RedactingFilter().filter(record)
    assert len(record.args) == 5
    assert "argsecret-42" not in record.getMessage()


SECRET_NAME = re.compile(r"_(USER|PASSWORD)$|SECRET|_KEY$")


def test_every_secret_like_setting_is_in_the_log_secret_list():
    """새 비밀 설정(`*_USER`·`*_PASSWORD`·`*SECRET*`·`*_KEY`)은 LOG_SECRET_SETTINGS 에 넣어야 한다."""
    import inspect

    from pydantic_settings import BaseSettings

    import config

    fields = {
        name
        for obj in vars(config).values()
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
        for name in obj.model_fields
        if SECRET_NAME.search(name)
    }
    listed = {name for _, name in config.LOG_SECRET_SETTINGS}
    assert fields, "전제 붕괴 — 비밀 설정을 하나도 못 찾았다"
    assert fields <= listed, f"LOG_SECRET_SETTINGS 에 없는 비밀 설정: {sorted(fields - listed)}"


def test_log_secret_values_reads_current_settings(monkeypatch):
    import config

    monkeypatch.setattr(config.db_settings, "MYSQL_PASSWORD", "pw-from-settings")
    monkeypatch.setattr(config.redis_settings, "REDIS_PASSWORD", None)
    values = config.log_secret_values()
    assert "pw-from-settings" in values
    assert None not in values and "" not in values


def test_configure_logging_installs_secret_values(monkeypatch, secrets):
    import config
    from app.utils.logs import setup as logs_setup

    monkeypatch.setattr(config.jwt_settings, "ACCESS_TOKEN_SECRET_KEY", "installed-secret-xyz")
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
    monkeypatch.setattr(logs_setup, "_configured", False)
    monkeypatch.setattr(logs_setup, "start_queue_listener", lambda handler: False)
    logs_setup.configure_logging()
    assert "installed-secret-xyz" not in redact("k=installed-secret-xyz!")


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


def test_removed_file_settings_are_gone():
    fields = LogSettings.model_fields
    for name in ("LOG_BACKUP_COUNT", "LOG_APP_FILENAME", "LOG_ERROR_FILENAME"):
        assert name not in fields
    assert fields["LOG_RETENTION_DAYS"].default == 30


# =============================================================================
# L1. 포맷 통일 — 앱 · python main.py · uvicorn main:app · Celery(메인+태스크), 콘솔·파일 모두
#
# 각 경로를 실제 순서대로 재현한다: 외부 도구가 먼저 자기 핸들러를 세우고(uvicorn LOGGING_CONFIG,
# Celery 의 root·celery.task 핸들러), 그다음 우리 구성이 적용된다. 출력은 root 콘솔(버퍼)과 실제
# 파일(tmp)에서 읽는다. 비밀값 원문(L7)이 어느 출력에도 없는지 같은 실행에서 본다.
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
        assert (app_line["app"], app_line["module"]) == ("app", "test_logging_overhaul")
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


def test_listener_is_restarted_after_fork():
    """prefork 자식은 listener 스레드를 물려받지 못한다 — 같은 큐·핸들러로 다시 세운다."""
    import queue
    from logging.handlers import QueueListener

    from app.utils.logs import queue_logging

    io_buffer = io.StringIO()
    buf_handler = logging.StreamHandler(io_buffer)
    inherited = QueueListener(queue.Queue(), buf_handler)  # fork 로 복제된, 스레드 없는 listener
    saved = queue_logging._listener
    queue_logging._listener = inherited
    try:
        assert queue_logging.restart_queue_listener_after_fork() is True
        inherited.queue.put_nowait(logging.makeLogRecord({"msg": "from-child"}))
        queue_logging.stop_queue_listener_sync()
    finally:
        queue_logging._listener = saved
    assert "from-child" in io_buffer.getvalue()


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
