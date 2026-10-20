"""환경별 로깅 dictConfig 빌더 — 설정 단일 지점.

ENV(development/test/staging/production)에 따라 레벨·핸들러·타임존을 다르게 구성한다.
- development (uv run fastapi dev): 콘솔, DEBUG, 밀리초, 로컬 TZ(KST)
- test: 콘솔, 간결, 파일 off, 로컬 TZ
- staging/production: 콘솔 + 회전 파일 + 에러 파일, INFO, UTC

Django 와 같은 점 / 다른 점 (ADR-019 — 이 설계를 유지하기로 확정했다):
    같다   — 설정이 한 곳에 모인다. Django 의 ``settings.LOGGING`` 자리를
             ``build_dictconfig()`` 가 맡고, ``configure_logging()`` 이 1회 적용한다.
    다르다 — **앱별 로거를 등록하지 않는다.** 아래 dict 에 ``loggers`` 키가 없고
             핸들러는 **root 에만** 붙는다. ``get_logger(name)`` 이 돌려주는 것은
             NOTSET·핸들러 0·propagate=True 인 자식 로거이며, 로그 헤더의 ``app=`` 은
             로거 이름이 아니라 **소스 파일 경로**에서 산출된다
             (``filters.ContextFilter`` → ``_app_from_path``).

왜 이렇게 하나:
    새 기능을 추가할 때 로깅 설정에 **손댈 곳이 0** 이다. Django 라면 ``LOGGING["loggers"]``
    에 한 줄을 더해야 하고, 그 한 줄을 빠뜨리면 조용히 기본값으로 흘러간다. 경로 기반
    판별은 등록 누락이라는 실패 모드 자체를 없앤다. 로거 이름을 잘못 줘도(복사·붙여넣기)
    ``app=`` 라벨은 항상 맞다.

앱별·라이브러리별 레벨 (logging-overhaul L4 — 위 포기 항목을 사용자 결정으로 대체):
    ``loggers`` 키를 더하지 않고 **헤더(app=) 이름 기준 필터**로 준다 — ``LOG_APP_LEVELS="blog=DEBUG,
    sqlalchemy=WARNING"`` → ``filters.AppLevelFilter``(모든 핸들러, ContextFilter 바로 뒤). root 레벨은
    LOG_LEVEL 과 헤더별 레벨의 최솟값으로 내린다. 라이브러리 헤더는 로거 이름에서 나온다(``_app_from_path``).
    그래서 새 기능을 추가할 때 손댈 곳이 0 이라는 성질은 그대로다.
"""

from __future__ import annotations

import logging
import sys

from config import LogSettings, app_settings, log_settings

# 기본 포맷 (#3): [시간 TZ] LEVEL [app=..] [module:class:func:line] message
# 실제로 쓰는 값은 LOG_CONSOLE_FORMAT·LOG_FILE_FORMAT 이다 — 이 상수는 그 기본값이다.
LOG_FORMAT: str = LogSettings.model_fields["LOG_CONSOLE_FORMAT"].default

# 프로세스 종류 → (본 로그, 에러 로그) 파일 이름 (logging-overhaul L5, ADR-001).
# 에러 파일도 프로세스별로 나눈다 — 웹과 워커가 한 파일을 함께 회전시키지 않게.
LOG_FILES = {
    "app": ("app.log", "error.log"),
    "celery": ("celery.log", "celery-error.log"),
}


def process_from_argv(argv: list[str]) -> str:
    """진입점으로 프로세스 종류를 정한다 — ``celery`` CLI·``python -m celery`` 면 celery, 그 밖은 app.

    로깅 신호(on_setup_logger)를 기다리면 그 전에 찍힌 기동 초기 줄(설정 로드·라우팅 구성)이 웹 파일로
    간다(integration-e2e F-006). 모듈 import 가 아니라 argv 로 정하므로 웹이 Celery 모듈을 import 해도
    웹 줄은 그대로 app.log 다.
    """
    if not argv:
        return "app"
    entry = argv[0].replace("\\", "/").lower()
    name = entry.rsplit("/", 1)[-1]
    if name in ("celery", "celery.exe") or entry.endswith("/celery/__main__.py"):
        return "celery"
    return "app"


# 이 프로세스의 종류. 진입점이 정하고(process_from_argv), Celery 신호 수신자가 한 번 더 확정한다(set_process).
_process = process_from_argv(sys.argv)


def set_process(kind: str) -> None:
    """진입점이 프로세스 종류를 정한다 — 파일 이름(LOG_FILES)이 따른다."""
    global _process
    if kind not in LOG_FILES:
        raise ValueError(f"모르는 프로세스 종류: {kind!r} (가능: {', '.join(LOG_FILES)})")
    _process = kind


def _env() -> str:
    return getattr(app_settings, "ENV", "development")


def _level() -> str:
    return log_settings.get_effective_log_level(app_settings.DEBUG)


def _min_level() -> str:
    """로거(root) 레벨 — LOG_LEVEL 과 LOG_APP_LEVELS 중 가장 낮은 값. 거르기는 AppLevelFilter 가 한다."""
    names = logging.getLevelNamesMapping()
    return min([_level(), *log_settings.get_app_levels().values()], key=names.__getitem__)


def console_enabled() -> bool:
    """콘솔(stdout/stderr) 핸들러를 붙일지 — 콘솔을 만드는 **모든 경로**가 이 함수 하나만 본다.

    콘솔 핸들러는 root 에 하나뿐이다(build_dictconfig). uvicorn(두 실행 경로)·Celery 워커의 줄도
    root 로 전파되므로(setup.adopt_external_handlers·configure_worker_logging) 같이 따른다.
    """
    return log_settings.LOG_CONSOLE_ENABLED


def file_enabled() -> bool:
    """파일 핸들러를 붙이는가 — staging/production 이고 LOG_FILE_ENABLED 일 때만."""
    return _env() in ("production", "staging") and log_settings.LOG_FILE_ENABLED


def _formatter(fmt: str, *, use_utc: bool, with_ms: bool = False) -> dict:
    return {
        "()": "app.utils.logs.formatters.TzFormatter",
        "fmt": fmt,
        "datefmt": log_settings.LOG_DATE_FORMAT,
        "use_utc": use_utc,
        "with_ms": with_ms,
    }


def build_dictconfig(logfile: str | None = None) -> dict:
    """root 구성 — 모든 실행 경로가 이 핸들러 한 벌을 쓴다(logging-overhaul L1).

    Args:
        logfile: Celery ``--logfile``. 주면 파일 형식·필터로 root 에 직접 붙인다(ENV 무관).
    """
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    with_ms = env == "development"

    handlers: dict = {}
    root_handlers: list[str] = []
    if console_enabled():
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "filters": ["context", "app_levels", "redact", "sql_noise"],
            "level": log_settings.get_effective_console_level(app_settings.DEBUG),
        }
        root_handlers.append("console")

    if file_enabled():
        log_dir = log_settings.get_log_dir()
        main_file, error_file = LOG_FILES[_process]
        for name, filename, file_level in (
            ("file", main_file, log_settings.LOG_FILE_LEVEL),
            ("error_file", error_file, "ERROR"),
        ):
            handlers[name] = {
                "()": "app.utils.logs.handlers.DailyRotatingFileHandler",
                "filename": str(log_dir / filename),
                "max_bytes": log_settings.LOG_MAX_SIZE_MB * 1024 * 1024,
                "retention_days": log_settings.LOG_RETENTION_DAYS,
                "formatter": "file",
                "filters": ["context", "redact"],
                "level": file_level,
            }
        # 파일 핸들러를 root 에 **직접 붙이지 않는다.** 붙이면 로그를 남기는 코루틴이
        # 파일 쓰기와 로테이션을 직접 수행해 event loop 가 그만큼 멈춘다.
        # queue handler 가 레코드를 큐에 넣고(빠름), listener 가 별도 스레드에서
        # 실제 파일 I/O 를 한다 (ADR-003).
        handlers["queue"] = {
            "class": "app.utils.logs.queue_logging.BoundedQueueHandler",
            "queue": {"()": "app.utils.logs.queue_logging.make_log_queue"},
            "handlers": ["file", "error_file"],
            "respect_handler_level": True,
            # 소음 차단·앱별 레벨은 큐 **앞에서** 한다. 뒤에서 하면 버릴 레코드까지 큐 자리를
            # 차지해 정작 필요한 로그가 상한에 걸려 드롭된다. context 도 앞에서 채운다 — listener
            # 스레드에서 채우면 classname 을 호출 스택이 아니라 listener 스택에서 찾는다.
            "filters": ["context", "app_levels", "sql_noise"],
        }
        root_handlers += ["queue"]

    if logfile:
        handlers["logfile"] = {
            "class": "logging.handlers.WatchedFileHandler",  # Celery 가 --logfile 에 쓰는 것과 같다
            "filename": logfile,
            "encoding": "utf-8",
            "formatter": "file",
            "filters": ["context", "app_levels", "redact", "sql_noise"],
        }
        root_handlers.append("logfile")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
            "app_levels": {
                "()": "app.utils.logs.filters.AppLevelFilter",
                "levels": log_settings.get_app_levels(),
                "default": level,
            },
            "redact": {"()": "app.utils.logs.filters.RedactingFilter"},
            "sql_noise": {"()": "app.utils.logs.filters.SQLNoiseFilter"},
        },
        "formatters": {
            "app": _formatter(log_settings.LOG_CONSOLE_FORMAT, use_utc=use_utc, with_ms=with_ms),
            "file": _formatter(log_settings.LOG_FILE_FORMAT, use_utc=use_utc, with_ms=with_ms),
        },
        "handlers": handlers,
        "root": {"handlers": root_handlers, "level": _min_level()},
    }
