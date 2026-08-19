"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

from app.utils.logs.config import LOG_FORMAT, _env, _level, build_dictconfig
from app.utils.logs.queue_logging import BoundedQueueHandler, start_queue_listener

_configured = False


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
    dictConfig(build_dictconfig())
    _configured = True
    start_queue_listener(_queue_handler())


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
    """Uvicorn(log_config)용 dictConfig. 앱 포맷과 동일한 헤더를 사용한다."""
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
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
            "default": {
                "()": "app.utils.logs.formatters.TzFormatter",
                "fmt": LOG_FORMAT,
                "use_utc": use_utc,
            },
            "access": {
                "()": "app.utils.logs.formatters.TzFormatter",
                "fmt": access_fmt,
                "use_utc": use_utc,
            },
        },
        "handlers": {
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
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": level, "propagate": False},
        },
    }
