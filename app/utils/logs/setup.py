"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).

모든 실행 경로가 root 의 핸들러 한 벌(같은 포매터·필터)로 찍는다(logging-overhaul L1):
    앱 로거            — root 로 전파
    python main.py     — uvicorn 에 log_config 를 주지 않는다 → uvicorn 로거가 root 로 전파
    uvicorn main:app   — CLI 가 먼저 붙인 핸들러를 adopt_external_handlers() 가 걷고 root 로 전파
    Celery 워커        — 로깅 신호 수신자가 프로세스를 celery 로 정하고 root 를 다시 구성
                         (--logfile 은 같은 파일 형식으로 유지), celery.task 는 root 로 전파
"""

from __future__ import annotations

import logging
import multiprocessing
import sys
from logging.config import dictConfig

from app.utils.logs.config import (
    _env,
    build_dictconfig,
    console_enabled,
    file_enabled,
    set_process,
)
from app.utils.logs.filters import known_app_names, set_secret_values
from app.utils.logs.queue_logging import (
    BoundedQueueHandler,
    start_queue_listener,
    stop_queue_listener_sync,
)
from config import log_secret_values, log_settings

_configured = False

# uvicorn CLI 가 자기 핸들러를 붙이는 로거(propagate=False).
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(force: bool = False, logfile: str | None = None) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent).

    파일 로깅이 켜진 환경에서는 queue listener 도 함께 시작한다. `python main.py` 와
    `uvicorn main:app` 은 진입 경로가 다르지만 둘 다 결국 `get_logger()` 를 거치므로,
    bootstrap 을 여기 한 곳에 두면 **어느 경로로 들어와도 정확히 한 번** 일어난다
    (계획서 §8). listener 시작은 그 자체로도 멱등이라 이중 방어가 된다.

    Args:
        force: 이미 구성됐어도 다시 적용한다(이전 listener 는 멈춰 flush 한다).
        logfile: Celery ``--logfile`` — 같은 파일 형식·필터로 root 에 붙인다.
    """
    global _configured
    if _configured and not force:
        return
    set_secret_values(log_secret_values())
    if force:
        stop_queue_listener_sync()
    dictConfig(build_dictconfig(logfile=logfile))
    if file_enabled() and multiprocessing.parent_process() is not None:
        # uvicorn --workers 2 이상은 워커를 spawn 한다 — 같은 파일을 여러 프로세스가 회전시킨다.
        logging.getLogger(__name__).warning(
            "파일 로그가 켜진 채 여러 프로세스로 실행 중입니다 — 같은 로그 파일을 여러 프로세스가"
            " 회전시키면 안전하지 않습니다. LOG_FILE_ENABLED=false 로 두고 stdout 을 수집하세요."
        )
    if not console_enabled() and not file_enabled():
        # 조용히 로그를 잃지 않게 — 기동은 하되 한 번 알린다(logging 은 꺼져 있으니 stderr 로 직접).
        sys.stderr.write(
            "[logging] 경고: LOG_CONSOLE_ENABLED=false 이고 파일 로그도 없어"
            f" (ENV={_env()}, LOG_FILE_ENABLED={log_settings.LOG_FILE_ENABLED})"
            " 로그가 어디에도 출력되지 않습니다.\n"
        )
    # 모르는 헤더는 경고만 한다 — 아직 없는 기능 이름을 미리 적어 둘 수 있다.
    unknown = sorted(set(log_settings.get_app_levels()) - known_app_names())
    if unknown:
        logging.getLogger(__name__).warning(
            "LOG_APP_LEVELS 에 모르는 헤더가 있습니다(무시하지 않고 그대로 둡니다): %s", unknown
        )
    # `uvicorn main:app`(CLI)·`fastapi dev` 는 앱 import **전에** 자기 핸들러를 uvicorn 로거에
    # 붙인다(propagate=False). 걷어내고 root 로 보낸다 — 형식·헤더·마스킹·앱별 레벨·파일이 같아진다.
    # `python main.py` 는 uvicorn 에 log_config 를 주지 않으므로 걷을 것이 없다(멱등).
    adopt_external_handlers(*(logging.getLogger(name) for name in UVICORN_LOGGERS))
    _configured = True
    start_queue_listener(_queue_handler())


def adopt_external_handlers(*loggers: logging.Logger) -> None:
    """우리 dictConfig 밖에서 붙은 핸들러(uvicorn CLI·Celery celery.task)를 걷고 root 로 전파시킨다(멱등).

    root 에는 콘솔·파일 핸들러가 이미 있다 — 남겨 두면 같은 줄이 다른 형식으로 두 번 찍히고,
    걷기만 하면(propagate=False) 줄이 사라진다.
    """
    for logger in loggers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        logger.propagate = True


def configure_worker_logging(logfile: str | None = None) -> None:
    """Celery 워커 — 프로세스 종류를 celery 로 정하고 root 를 다시 구성한다(celery.log·celery-error.log).

    Celery 는 root 를 가로채 자기 핸들러를 단다(worker_hijack_root_logger). 그 핸들러를 우리 구성으로
    바꾸되 ``--logfile`` 은 같은 파일 형식으로 유지한다.
    """
    set_process("celery")
    configure_logging(force=True, logfile=logfile)


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
