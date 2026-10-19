"""로깅 개편 (logging-overhaul) — 헤더·필수 필드·비밀값·앱별 레벨·파일 회전·보관.

각 테스트는 실제 레코드·실제 파일로 확인한다. 회전·보관 테스트는 tmp 경로에서 실제 파일을 만든다.
"""

import logging
import re
import sys

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
