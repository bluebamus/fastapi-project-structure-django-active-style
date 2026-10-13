"""로그 비밀정보 마스킹 (C-5, residual-risk R-007).

지금은 SQLAlchemy `echo=False` 라 SQL 이 로그로 나가지 않는다. 그건 **설정**에
기댄 차단이라 누가 echo 를 켜는 순간 무너진다. 구조적으로 막기 위해 로깅 파이프라인
자체에서 DSN 자격증명과 secret 형태의 값을 지운다.
"""

import io
import logging
import re
import sys
from contextlib import contextmanager
from logging.config import dictConfig
from pathlib import Path

import pytest

from app.utils.logs.filters import RedactingFilter, redact

SENTINEL = "sup3rs3cret-sentinel"


def _record(msg, *args):
    return logging.LogRecord(
        name="probe",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def _filtered(msg, *args):
    record = _record(msg, *args)
    assert RedactingFilter().filter(record) is True
    return record.getMessage()


@pytest.mark.parametrize(
    "dsn",
    [
        f"mysql+aiomysql://app:{SENTINEL}@db:3306/shop",
        f"postgresql://user:{SENTINEL}@127.0.0.1:5432/x",
        f"redis://default:{SENTINEL}@cache:6379/0",
    ],
)
def test_dsn_password_is_masked(dsn):
    out = _filtered("connecting: %s", dsn)

    assert SENTINEL not in out
    assert "***" in out
    # 진단에 필요한 나머지는 남긴다 — 통째로 지우면 로그가 쓸모없어진다.
    assert "db:3306" in out or "127.0.0.1:5432" in out or "cache:6379" in out


@pytest.mark.parametrize(
    "template",
    [
        "password={}",
        "PASSWORD: {}",
        "secret={}",
        "token={}",
        "api_key={}",
        "api-key: '{}'",
        'SECRET_KEY="{}"',
    ],
)
def test_keyword_secrets_are_masked(template):
    out = _filtered(template.format(SENTINEL))

    assert SENTINEL not in out
    assert "***" in out


def test_message_without_secret_is_untouched():
    message = "라우터 include 완료: 6개"

    assert _filtered(message) == message


def test_args_are_folded_after_redaction():
    """치환 후에는 args 를 비워 포매터가 두 번 전개하지 않게 한다."""
    record = _record("dsn=%s", f"mysql://u:{SENTINEL}@h/db")
    RedactingFilter().filter(record)

    assert record.args in ((), None)
    assert SENTINEL not in record.getMessage()


def test_dsn_without_password_is_untouched():
    dsn = "sqlite+aiosqlite:///:memory:"

    assert _filtered("connecting: %s", dsn) == f"connecting: {dsn}"


def test_filter_is_wired_into_logging_config():
    """dictConfig 에 실제로 물려 있어야 의미가 있다."""
    from app.utils.logs import config as log_config
    from app.utils.logs import setup as log_setup

    for module in (log_config, log_setup):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "RedactingFilter" in source, f"{module.__name__} 에 필터가 연결되지 않았습니다."


# =============================================================================
# traceback·stack 마스킹 (log-redaction-fixes ADR-002)
#
# 예외 메시지·체인(`raise ... from`)·stack_info 에 실린 비밀값이 **실제 핸들러 경로**마다
# 가려지는지 본다. 각 경로는 프로젝트가 쓰는 dictConfig 를 그대로 적용해 만든다.
# 진단 정보(예외 타입·파일·줄·체인 문구)는 남아야 한다.
# =============================================================================
PASSWORD = "secret42"
DSN = f"mysql+asyncmy://u:{PASSWORD}@h/db"
BEARER = "xxx-bearer-token-42"


def _raise_chained():
    try:
        raise ConnectionError(f"connect to {DSN} failed")
    except ConnectionError as inner:
        raise RuntimeError(f"password={PASSWORD} Authorization: Bearer {BEARER}") from inner


def _emit(logger: logging.Logger) -> None:
    try:
        _raise_chained()
    except RuntimeError:
        logger.exception("unhandled")
    logger.error("stack probe", stack_info=True)  # password=secret42 — stack 의 소스 줄


def _assert_redacted(text: str) -> None:
    assert PASSWORD not in text, text
    assert BEARER not in text, text
    assert "***" in text
    # 진단 정보는 남는다.
    assert "RuntimeError" in text and "ConnectionError" in text
    assert "direct cause" in text, "체인 예외가 사라졌습니다."
    assert re.search(rf'{re.escape(Path(__file__).name)}", line \d+', text), "파일·줄이 없습니다."
    assert "Stack (most recent call last)" in text


@contextmanager
def _isolated_loggers(*names: str):
    """root 와 지정 로거의 핸들러·레벨·전파를 저장했다가 되돌린다."""
    loggers = [logging.getLogger(), *(logging.getLogger(n) for n in names)]
    saved = [(lg, lg.handlers[:], lg.level, lg.propagate, lg.disabled) for lg in loggers]
    try:
        yield
    finally:
        for lg, handlers, level, propagate, disabled in saved:
            for handler in lg.handlers:
                if handler not in handlers:
                    handler.close()
            lg.handlers[:] = handlers
            lg.setLevel(level)
            lg.propagate = propagate
            lg.disabled = disabled


def _capture(logger: logging.Logger) -> io.StringIO:
    buf = io.StringIO()
    for handler in logger.handlers:
        if type(handler) is logging.StreamHandler:
            handler.setStream(buf)
    return buf


def _app_config_on_probe_logger(cfg: dict) -> dict:
    """root 대신 전용 로거에 같은 핸들러를 붙인다 — 테스트 프로세스의 root 를 건드리지 않게."""
    cfg["loggers"] = {"redaction-probe": {**cfg.pop("root"), "level": "DEBUG", "propagate": False}}
    return cfg


def test_bearer_token_is_masked():
    out = redact(f"Authorization: Bearer {BEARER}")

    assert BEARER not in out
    assert out == "Authorization: Bearer ***"


def test_filter_masks_exc_text_chain_and_stack_info():
    """필터가 traceback 을 미리 렌더해 가리고, 포매터는 그 결과를 그대로 쓴다."""
    record = None
    try:
        _raise_chained()
    except RuntimeError:
        record = logging.LogRecord("probe", logging.ERROR, __file__, 1, "x", (), sys.exc_info())
    record.stack_info = f"Stack (most recent call last):\n  dsn={DSN}"

    assert RedactingFilter().filter(record) is True
    out = logging.Formatter().format(record)

    assert PASSWORD not in out and BEARER not in out
    assert "***" in out and "direct cause" in out and "RuntimeError" in out


def test_development_console_handler_masks_traceback(monkeypatch, tmp_path):
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config.app_settings, "ENV", "development", raising=False)
    with _isolated_loggers("redaction-probe"):
        dictConfig(_app_config_on_probe_logger(logs_config.build_dictconfig()))
        probe = logging.getLogger("redaction-probe")
        buf = _capture(probe)
        _emit(probe)

    _assert_redacted(buf.getvalue())


def test_production_console_and_file_handlers_mask_traceback(monkeypatch, tmp_path):
    from app.utils.logs import config as logs_config
    from app.utils.logs.queue_logging import BoundedQueueHandler

    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    with _isolated_loggers("redaction-probe"):
        dictConfig(_app_config_on_probe_logger(logs_config.build_dictconfig()))
        probe = logging.getLogger("redaction-probe")
        buf = _capture(probe)
        queue_handler = next(h for h in probe.handlers if isinstance(h, BoundedQueueHandler))
        listener = queue_handler.listener
        listener.start()
        try:
            _emit(probe)
        finally:
            listener.stop()
            for handler in listener.handlers:
                handler.close()

    _assert_redacted(buf.getvalue())
    files = sorted(tmp_path.iterdir())
    assert len(files) == 2, files  # app 로그·error 로그
    for path in files:
        _assert_redacted(path.read_text(encoding="utf-8"))


def test_uvicorn_log_config_masks_traceback():
    """`python main.py` 경로 — setup_uvicorn_logging() 의 핸들러."""
    from app.utils.logs import setup_uvicorn_logging

    with _isolated_loggers("uvicorn", "uvicorn.error", "uvicorn.access"):
        dictConfig(setup_uvicorn_logging())
        error_logger = logging.getLogger("uvicorn.error")
        buf = _capture(error_logger)
        _emit(error_logger)

    _assert_redacted(buf.getvalue())


def test_uvicorn_cli_default_handlers_get_the_filter(monkeypatch):
    """`uvicorn main:app` 경로 — uvicorn 이 앱 import 전에 세운 기본 핸들러에도 마스킹이 붙는다."""
    import uvicorn.config

    from app.utils.logs import setup as logs_setup

    with _isolated_loggers("uvicorn", "uvicorn.error", "uvicorn.access"):
        dictConfig(uvicorn.config.LOGGING_CONFIG)  # uvicorn Config.__init__ 이 하는 일
        # 앱 import 가 부르는 configure_logging() — root 재구성은 막고 나머지 단계만 본다.
        monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
        monkeypatch.setattr(logs_setup, "_configured", False)
        logs_setup.configure_logging()
        error_logger = logging.getLogger("uvicorn.error")
        # 기본 설정에서 uvicorn.error 는 핸들러 없이 "uvicorn" 로 전파한다.
        buf = _capture(logging.getLogger("uvicorn"))
        _emit(error_logger)

    _assert_redacted(buf.getvalue())


def test_celery_worker_handlers_get_the_filter():
    """Celery 워커가 root 를 가로채며 붙인 핸들러에도 같은 필터가 붙는다(after_setup_logger)."""
    from celery.signals import after_setup_logger, after_setup_task_logger

    from app.celery.worker_lifecycle import on_setup_logger, register_worker_signals

    register_worker_signals()
    for signal in (after_setup_logger, after_setup_task_logger):
        assert on_setup_logger in [receiver for _, receiver in signal.receivers]

    with _isolated_loggers("celery-probe"):
        probe = logging.getLogger("celery-probe")
        probe.propagate = False
        probe.setLevel(logging.DEBUG)
        buf = io.StringIO()
        probe.addHandler(logging.StreamHandler(buf))  # Celery 가 붙이는 핸들러 자리
        on_setup_logger(logger=probe)
        on_setup_logger(logger=probe)  # 멱등 — 필터가 두 번 붙지 않는다
        assert len(probe.handlers[0].filters) == 1
        _emit(probe)

    _assert_redacted(buf.getvalue())
