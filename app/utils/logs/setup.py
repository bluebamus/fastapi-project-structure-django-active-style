"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).
"""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig

from app.utils.logs.config import (
    _env,
    _formatter,
    _level,
    build_dictconfig,
    console_enabled,
    file_enabled,
)
from app.utils.logs.filters import redact_handlers, set_secret_values
from app.utils.logs.queue_logging import BoundedQueueHandler, start_queue_listener
from config import log_secret_values, log_settings

_configured = False

# uvicorn 이 자기 핸들러를 붙이는 로거(propagate=False).
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(force: bool = False) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent).

    파일 로깅이 켜진 환경에서는 queue listener 도 함께 시작한다. `python main.py` 와
    `uvicorn main:app` 은 진입 경로가 다르지만 둘 다 결국 `get_logger()` 를 거치므로,
    bootstrap 을 여기 한 곳에 두면 **어느 경로로 들어와도 정확히 한 번** 일어난다
    (계획서 §8). listener 시작은 그 자체로도 멱등이라 이중 방어가 된다.
    """
    global _configured
    if _configured and not force:
        return
    set_secret_values(log_secret_values())
    dictConfig(build_dictconfig())
    if not console_enabled() and not file_enabled():
        # 조용히 로그를 잃지 않게 — 기동은 하되 한 번 알린다(logging 은 꺼져 있으니 stderr 로 직접).
        sys.stderr.write(
            "[logging] 경고: LOG_CONSOLE_ENABLED=false 이고 파일 로그도 없어"
            f" (ENV={_env()}, LOG_FILE_ENABLED={log_settings.LOG_FILE_ENABLED})"
            " 로그가 어디에도 출력되지 않습니다.\n"
        )
    # `uvicorn main:app`(CLI) 은 앱 import **전에** 자기 기본 핸들러를 uvicorn 로거에 붙인다
    # (propagate=False). 그 핸들러에도 같은 규칙(마스킹·콘솔 on/off)을 적용한다 — 안 그러면
    # "Exception in ASGI application" traceback 이 가려지지 않은 채 찍힌다. `python main.py`
    # 경로는 setup_uvicorn_logging() 이 이미 맞춰 두므로 아무 일도 하지 않는다(멱등).
    adopt_external_handlers(*(logging.getLogger(name) for name in UVICORN_LOGGERS))
    _configured = True
    start_queue_listener(_queue_handler())


def _is_console(handler: logging.Handler) -> bool:
    # FileHandler 도 StreamHandler 의 하위 클래스다 — 파일은 콘솔이 아니다.
    return isinstance(handler, logging.StreamHandler) and not isinstance(
        handler, logging.FileHandler
    )


def adopt_external_handlers(*loggers: logging.Logger) -> None:
    """우리 dictConfig 밖에서 붙은 핸들러(uvicorn CLI·Celery 워커)를 같은 규칙에 맞춘다(멱등).

    콘솔이 꺼져 있으면(console_enabled) 콘솔 핸들러를 걷어내고, 핸들러가 하나도 안 남은 로거는
    root 로 전파시켜 파일 핸들러가 있으면 거기에 남게 한다. 남은 핸들러에는 마스킹을 단다.
    형식은 바꾸지 않는다 — uvicorn·Celery 의 기본 출력은 그대로다.
    """
    if not console_enabled():
        for logger in loggers:
            for handler in [h for h in logger.handlers if _is_console(h)]:
                logger.removeHandler(handler)
            if not logger.handlers:
                logger.propagate = True
    redact_handlers(*loggers)


def _queue_handler() -> BoundedQueueHandler | None:
    """root 에 붙은 queue handler(없으면 None — development/test)."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, BoundedQueueHandler):
            return handler
    return None


def get_logger(name: str = "app") -> logging.Logger:
    """설정된 로깅을 공유하는 로거를 반환한다.

    Args:
        name: 로거 이름(모듈명 권장). 헤더의 app 은 소스 경로에서 자동 산출된다.
    """
    configure_logging()
    return logging.getLogger(name)


def setup_uvicorn_logging() -> dict:
    """Uvicorn(log_config)용 dictConfig. 앱 콘솔 포맷(LOG_CONSOLE_FORMAT)과 날짜 형식을 쓴다.

    콘솔이 꺼져 있으면 핸들러 없이 root 로 전파한다 — 파일 핸들러가 있으면 거기에만 남는다.
    """
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    console = console_enabled()
    access_fmt = (
        "[{asctime} {tzname}] {levelname:5} [app=uvicorn] "
        '{client_addr} - "{request_line}" {status_code}'
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
            "redact": {"()": "app.utils.logs.filters.RedactingFilter"},
        },
        "formatters": {
            "default": _formatter(log_settings.LOG_CONSOLE_FORMAT, use_utc=use_utc),
            # 접속 줄은 args 를 요청 라인 필드로 푸는 전용 포매터가 필요하다(R-804).
            "access": {
                **_formatter(access_fmt, use_utc=use_utc),
                "()": "app.utils.logs.formatters.TzAccessFormatter",
            },
        },
        "handlers": {}
        if not console
        else {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "filters": ["context", "redact"],
            },
            "access": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "access",
                "filters": ["context", "redact"],
            },
        },
        "loggers": {
            name: {
                "handlers": [handler] if console else [],
                "level": level,
                "propagate": not console,
            }
            for name, handler in (
                ("uvicorn", "default"),
                ("uvicorn.error", "default"),
                ("uvicorn.access", "access"),
            )
        },
    }
