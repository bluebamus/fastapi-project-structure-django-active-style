"""로그 레코드 문맥 — 경로·로거 이름으로 정하는 `app=` 라벨, 클래스명 주입, 기본 포맷, ENV 별 핸들러,
SQL 소음 필터.
"""

import io
import logging
import pathlib

import pytest

from app.utils.logs import (
    LOG_FORMAT,
    ContextFilter,
    LoggerMixin,
    TzFormatter,
    get_logger,
)
from app.utils.logs import config as logs_config
from app.utils.logs import setup as logs_setup
from app.utils.logs.filters import (
    SQLNoiseFilter,
    _app_from_path,
)


def _rec(pathname="/x/app/features/blog/services/item_service.py", func="create"):
    return logging.LogRecord("blog", logging.INFO, pathname, 10, "hello", (), None, func)


def test_appname_from_path():
    assert _app_from_path("/x/app/features/blog/services/item_service.py") == "blog"
    assert _app_from_path("C:\\x\\app\\core\\bootstrap.py") == "core"
    assert _app_from_path("/x/app/celery/tasks.py") == "celery"
    assert _app_from_path("/x/app/utils/pagination/paginator.py") == "utils"
    assert _app_from_path("/x/migrations/env.py") == "migrations"


def test_repo_root_modules_are_not_labeled_external():
    """저장소 루트의 모듈이 'ext'(서드파티)로 분류되면 안 된다 (LOG-2).

    ``main.py``·``config.py`` 는 경로에 ``/app/`` 조각이 없어서, 예전 판별식에서
    서드파티로 빠졌다. 그러면 appname 으로 '우리 코드'를 거를 수 없다.
    이 테스트는 ``filters.py`` 가 다른 깊이로 옮겨져 ``_REPO_ROOT`` 계산이
    어긋나는 경우도 함께 잡는다.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    for name in ("main.py", "config.py"):
        assert (repo_root / name).is_file(), f"{name} 이 저장소 루트에 없다 — 테스트 전제 붕괴"
        assert _app_from_path(str(repo_root / name)) == "app"


def test_installed_packages_are_external():
    """저장소 루트 **안**의 .venv 도 서드파티로 분류된다."""
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    vendored = repo_root / ".venv" / "Lib" / "site-packages" / "sqlalchemy" / "engine.py"
    assert _app_from_path(str(vendored)) == "ext"
    assert _app_from_path("/opt/py/lib/python3.14/site-packages/httpx/_client.py") == "ext"


class _Caller:
    def run(self) -> str:
        rec = _rec()
        ContextFilter().filter(rec)
        return rec.classname


def test_classname_extracted_from_calling_class():
    """방식 A — 호출 클래스의 메서드에서 자동으로 클래스명을 채운다."""
    assert _Caller().run() == "_Caller"


def test_classname_dash_for_free_function():
    rec = _rec()
    ContextFilter().filter(rec)  # 모듈 레벨 호출(self 없음)
    assert rec.classname == "-"


def test_mixin_injects_classname():
    """방식 C — LoggerMixin 이 classname 을 extra 로 주입."""

    class _Svc(LoggerMixin):
        pass

    assert _Svc().log.extra["classname"] == "_Svc"


def test_format_contains_all_fields():
    rec = _rec()
    rec.appname = "blog"
    rec.classname = "ItemService"
    out = TzFormatter(LOG_FORMAT).format(rec)
    assert "app=blog" in out
    assert "item_service:ItemService:create:10" in out
    assert ("KST" in out) or ("UTC" in out)


def test_get_logger_end_to_end():
    logger = get_logger("test.e2e")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(ContextFilter())
    handler.setFormatter(TzFormatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("hello world")
    finally:
        logger.removeHandler(handler)
    text = buf.getvalue()
    assert "hello world" in text
    assert "app=" in text


# =============================================================================
# 환경별 dictConfig 구성
#
# staging/production 가지는 로컬·CI 에서 실행되지 않는다 — 즉 운영에서 처음 도는
# 코드다. dictConfig 를 실제로 적용하지 않고 **빌더가 만든 dict 만** 검사하므로
# 파일 핸들러가 열리지 않는다(파일 I/O 없음).
# =============================================================================
def _build_with(monkeypatch, tmp_path, **overrides):
    """ENV·로그 설정을 바꿔 build_dictconfig() 결과를 얻는다.

    빌더가 모듈 전역 settings 를 읽으므로 그 속성을 monkeypatch 로 갈아끼운다
    (monkeypatch 가 테스트 종료 시 되돌린다 — 싱글턴 오염 없음).
    """
    env = overrides.pop("env", "development")
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    # 로그 디렉터리는 tmp 로 — get_log_dir() 이 mkdir 을 하므로 저장소를 더럽히지 않게.
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in overrides.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


def test_production_adds_rotating_file_handlers(monkeypatch, tmp_path):
    """production 에서는 콘솔에 더해 회전 파일·에러 파일 핸들러가 붙고 UTC 를 쓴다.

    단, 파일 핸들러는 root 에 **직접 붙지 않는다** — queue 를 경유한다.
    아래 `test_file_handlers_are_behind_a_queue` 가 그 이유를 다룬다.
    """
    cfg = _build_with(monkeypatch, tmp_path, env="production", LOG_FILE_ENABLED=True)

    assert set(cfg["handlers"]) == {"console", "file", "error_file", "queue"}
    assert cfg["root"]["handlers"] == ["console", "queue"]
    assert cfg["formatters"]["app"]["use_utc"] is True

    for name in ("file", "error_file"):
        handler = cfg["handlers"][name]
        # 날짜 + 크기 + 보관일수
        assert handler["()"] == "app.utils.logs.handlers.DailyRotatingFileHandler"
        assert handler["retention_days"] == logs_config.log_settings.LOG_RETENTION_DAYS
        assert handler["max_bytes"] == logs_config.log_settings.LOG_MAX_SIZE_MB * 1024 * 1024
        # 핸들러마다 컨텍스트 필터가 붙어야 appname/classname 이 채워진다.
        assert handler["filters"] == ["context", "redact"]
        assert str(tmp_path) in handler["filename"]

    # 에러 전용 파일은 ERROR 만 받아야 의미가 있다.
    assert cfg["handlers"]["error_file"]["level"] == "ERROR"


def test_development_is_console_only_and_local_time(monkeypatch, tmp_path):
    """개발에서는 파일 핸들러를 붙이지 않고 로컬 TZ + 밀리초를 쓴다."""
    cfg = _build_with(monkeypatch, tmp_path, env="development")

    assert set(cfg["handlers"]) == {"console"}
    assert cfg["root"]["handlers"] == ["console"]
    assert cfg["formatters"]["app"]["use_utc"] is False
    assert cfg["formatters"]["app"]["with_ms"] is True


def test_file_logging_can_be_disabled_in_production(monkeypatch, tmp_path):
    """production 이라도 LOG_FILE_ENABLED=False 면 파일 핸들러를 만들지 않는다.

    읽기 전용 파일시스템(컨테이너)에서 기동이 깨지지 않으려면 이 스위치가 살아 있어야 한다.
    """
    cfg = _build_with(monkeypatch, tmp_path, env="production", LOG_FILE_ENABLED=False)

    assert set(cfg["handlers"]) == {"console"}
    assert cfg["root"]["handlers"] == ["console"]
    assert cfg["formatters"]["app"]["use_utc"] is True  # UTC 는 파일 여부와 무관


def test_configure_logging_applies_once(monkeypatch):
    """configure_logging() 은 여러 번 불러도 dictConfig 를 1회만 적용한다.

    get_logger() 가 매번 호출하므로, 여기서 idempotent 가 깨지면 로거를 만들 때마다
    전체 로깅이 재구성되어 런타임에 붙인 핸들러가 사라진다.
    """
    calls = []
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: calls.append(cfg))
    monkeypatch.setattr(logs_setup, "_configured", False, raising=False)

    logs_setup.configure_logging()
    logs_setup.configure_logging()
    get_logger("test.idempotent")
    assert len(calls) == 1

    # force=True 는 의도적 재적용이므로 통과해야 한다.
    logs_setup.configure_logging(force=True)
    assert len(calls) == 2


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


def _record(name: str, level: int) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, "SELECT * FROM users", None, None)


@pytest.mark.parametrize(
    "name",
    ["sqlalchemy.engine.Engine", "aiomysql.cursors", "pymysql.connections", "aiosqlite"],
)
@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO])
def test_sql_debug_and_info_are_blocked(name, level):
    """SQL 로그에는 바인딩된 파라미터가 그대로 실린다."""
    noise_filter = SQLNoiseFilter(allow_sql_echo=False)

    assert noise_filter.filter(_record(name, level)) is False


@pytest.mark.parametrize("level", [logging.WARNING, logging.ERROR, logging.CRITICAL])
def test_sql_warnings_and_above_pass_through(level):
    """커넥션 풀 고갈·재연결 실패는 장애 진단에 반드시 필요하다."""
    noise_filter = SQLNoiseFilter(allow_sql_echo=False)

    assert noise_filter.filter(_record("sqlalchemy.pool", level)) is True


def test_application_logs_are_untouched():
    """차단 대상은 SQL·드라이버 로거뿐이다."""
    noise_filter = SQLNoiseFilter(allow_sql_echo=False)

    assert noise_filter.filter(_record("app.features.blog", logging.DEBUG)) is True
    assert noise_filter.filter(_record("raw_repository", logging.DEBUG)) is True


def test_opt_in_lets_sql_debug_through():
    """development/test 에서 SQL 을 보고 싶을 때는 켤 수 있어야 한다."""
    noise_filter = SQLNoiseFilter(allow_sql_echo=True)

    assert noise_filter.filter(_record("sqlalchemy.engine.Engine", logging.DEBUG)) is True


def test_opt_in_is_ignored_outside_development(monkeypatch):
    """설정이 켜져 있어도 운영 환경이면 무시한다 — 배포 검증을 우회해도 여기서 걸린다."""
    from config import app_settings, log_settings

    monkeypatch.setattr(log_settings, "LOG_SQL_ECHO_ENABLED", True, raising=False)
    monkeypatch.setattr(app_settings, "ENV", "production", raising=False)

    noise_filter = SQLNoiseFilter()

    assert noise_filter.filter(_record("sqlalchemy.engine.Engine", logging.DEBUG)) is False
