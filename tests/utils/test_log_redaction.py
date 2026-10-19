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


def test_secret_inside_one_arg_is_masked_in_place():
    """비밀값이 인자 하나 안에 있으면 그 인자만 가리고 args 모양은 지킨다 (R-804).

    uvicorn 의 AccessFormatter 는 접속 줄의 args 5개를 풀어 요청 라인을 만든다 — args 를 비우면
    `?token=` 이 든 요청마다 logging 오류가 나고 그 줄이 사라진다.
    """
    record = _record("dsn=%s", f"mysql://u:{SENTINEL}@h/db")
    RedactingFilter().filter(record)

    assert record.args == ("mysql://***:***@h/db",)  # logging-overhaul L7 — 사용자명도 가린다
    assert SENTINEL not in record.getMessage()


def test_args_are_folded_when_secret_spans_template_and_arg():
    """`password=%s` 처럼 키워드는 틀에, 값은 인자에 있으면 인자만 봐서는 못 가린다 — 전개 후 가리고 args 를 비운다."""
    record = _record("password=%s", SENTINEL)
    RedactingFilter().filter(record)

    assert record.args in ((), None)
    assert SENTINEL not in record.getMessage()


def test_dsn_without_password_is_untouched():
    dsn = "sqlite+aiosqlite:///:memory:"

    assert _filtered("connecting: %s", dsn) == f"connecting: {dsn}"


def test_filter_is_wired_into_logging_config():
    """dictConfig 에 실제로 물려 있어야 의미가 있다."""
    from app.utils.logs import config as log_config

    # 모든 경로가 root 의 핸들러 한 벌(build_dictconfig)을 쓴다 (logging-overhaul L1).
    cfg = log_config.build_dictconfig(logfile="worker.log")
    assert cfg["filters"]["redact"]["()"].endswith("RedactingFilter")
    for name, handler in cfg["handlers"].items():
        if name != "queue":
            assert "redact" in handler["filters"], name


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


def test_masking_holds_with_user_log_formats(monkeypatch, tmp_path):
    """사용자 포맷(config-cleanup-2)으로 바꿔도 메시지·traceback·stack_info 는 가려진다.

    마스킹은 포매터가 아니라 필터가 하므로 형식과 무관해야 한다 — 위 production 테스트를 그대로 다시 돈다.
    """
    from app.utils.logs import config as logs_config

    for key in ("LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT"):
        monkeypatch.setattr(logs_config.log_settings, key, "{levelname}|{asctime}|{message}")
    monkeypatch.setattr(logs_config.log_settings, "LOG_DATE_FORMAT", "%d/%m/%Y")
    test_production_console_and_file_handlers_mask_traceback(monkeypatch, tmp_path)


def test_uvicorn_lines_through_root_mask_traceback():
    """`python main.py` 경로 — uvicorn 로거는 설정 없이 root 핸들러로 간다 (logging-overhaul L1)."""
    from app.utils.logs import config as logs_config

    with _isolated_loggers("uvicorn", "uvicorn.error", "uvicorn.access"):
        dictConfig(logs_config.build_dictconfig())
        buf = _capture(logging.getLogger())
        _emit(logging.getLogger("uvicorn.error"))

    _assert_redacted(buf.getvalue())


def test_uvicorn_cli_lines_are_masked_through_root():
    """`uvicorn main:app` 경로 — CLI 가 앱 import 전에 세운 기본 핸들러는 걷히고, 줄은 root(마스킹)로 간다."""
    import uvicorn.config

    from app.utils.logs import config as logs_config
    from app.utils.logs.setup import adopt_external_handlers

    with _isolated_loggers("uvicorn", "uvicorn.error", "uvicorn.access"):
        dictConfig(uvicorn.config.LOGGING_CONFIG)  # uvicorn Config.__init__ 이 하는 일
        dictConfig(logs_config.build_dictconfig())  # 앱 import 가 부르는 configure_logging()
        adopt_external_handlers(*(logging.getLogger(n) for n in ("uvicorn", "uvicorn.access")))
        buf = _capture(logging.getLogger())
        _emit(logging.getLogger("uvicorn.error"))

    _assert_redacted(buf.getvalue())


def test_celery_worker_handlers_get_the_filter():
    """Celery 워커 로거의 줄도 root 의 마스킹을 지난다(after_setup_logger·after_setup_task_logger)."""
    from celery.signals import after_setup_logger, after_setup_task_logger

    from app.celery.worker_lifecycle import on_setup_logger, register_worker_signals

    register_worker_signals()
    for signal in (after_setup_logger, after_setup_task_logger):
        assert on_setup_logger in [receiver for _, receiver in signal.receivers]

    from app.utils.logs import config as logs_config

    with _isolated_loggers("celery-probe"):
        dictConfig(logs_config.build_dictconfig())
        buf = _capture(logging.getLogger())
        probe = logging.getLogger("celery-probe")
        probe.propagate = False
        probe.addHandler(logging.StreamHandler(io.StringIO()))  # Celery 가 붙이는 핸들러 자리
        on_setup_logger(logger=probe)
        on_setup_logger(logger=probe)  # 멱등
        # 자기 핸들러는 걷히고 root(마스킹)로 전파된다 (logging-overhaul L1).
        assert probe.handlers == [] and probe.propagate is True
        _emit(probe)

    _assert_redacted(buf.getvalue())


# =============================================================================
# uvicorn 접속 줄 (R-804)
#
# uvicorn 은 접속 줄을 `'%s - "%s %s HTTP/%s" %d'` + args 5개로 남기고, 요청 라인 필드
# (client_addr·request_line·status_code)는 포매터가 args 를 풀어 만든다. 두 경로 모두 실제
# 모양 그대로 흘려 logging 오류 없이 찍히는지, 마스킹이 유지되는지 본다.
# =============================================================================
ACCESS_FMT = '%s - "%s %s HTTP/%s" %d'


def _access_line(monkeypatch, capsys, path: str, *, cli: bool, env: str = "production") -> str:
    import uvicorn.config

    from app.utils.logs import config as logs_config
    from app.utils.logs.setup import adopt_external_handlers

    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DATE_FORMAT", "%d/%m/%Y", raising=False)
    with _isolated_loggers("uvicorn", "uvicorn.error", "uvicorn.access"):
        if cli:
            dictConfig(uvicorn.config.LOGGING_CONFIG)  # `uvicorn main:app` — uvicorn 자체 포매터
        dictConfig(logs_config.build_dictconfig())  # 앱 import 의 configure_logging()
        if cli:
            # configure_logging() 이 하는 일 — 세 로거 모두(부모 "uvicorn" 이 propagate=False 라 함께 걷어야 한다)
            adopt_external_handlers(
                *(logging.getLogger(n) for n in ("uvicorn", "uvicorn.error", "uvicorn.access"))
            )
        access = logging.getLogger("uvicorn.access")
        buf = _capture(logging.getLogger())
        # uvicorn 코드에서 나온 레코드 그대로(설치 경로·args 5개) — 헤더가 로거 이름에서 나온다.
        site = "/opt/venv/lib/python3.14/site-packages/uvicorn/protocols/http/h11_impl.py"
        args = ("1.2.3.4:5", "GET", path, "1.1", 200)
        access.handle(
            logging.LogRecord(access.name, logging.INFO, site, 7, ACCESS_FMT, args, None, "send")
        )

    assert "Logging error" not in capsys.readouterr().err
    return buf.getvalue().strip()


@pytest.mark.parametrize(("env", "tz"), [("production", "UTC"), ("development", None)])
def test_python_main_access_line_is_formatted(monkeypatch, capsys, env, tz):
    """`python main.py` 경로 — 프로젝트 형식으로, {message} 는 요청 줄, 시간대·LOG_DATE_FORMAT 을 따른다."""
    from datetime import datetime

    from config import timezone_settings

    tz = tz or datetime.now(timezone_settings.tz).strftime("%Z")
    line = _access_line(monkeypatch, capsys, "/api/v1/health", cli=False, env=env)

    assert re.fullmatch(
        rf"\[\d{{2}}/\d{{2}}/\d{{4}}(\.\d{{3}})? {tz}\] INFO  \[app=uvicorn\] "
        r'\[h11_impl:-:send:7\] 1\.2\.3\.4:5 - "GET /api/v1/health HTTP/1\.1" 200',
        line,
    ), line


@pytest.mark.parametrize("cli", [False, True], ids=["python-main", "uvicorn-cli"])
def test_access_line_with_secret_query_is_masked(monkeypatch, capsys, cli):
    """쿼리 문자열의 비밀값은 가려지고 줄은 사라지지 않는다 — 두 경로 모두."""
    line = _access_line(monkeypatch, capsys, f"/api/v1/x?token={SENTINEL}", cli=cli)

    assert SENTINEL not in line
    assert line.endswith('"GET /api/v1/x?token=*** HTTP/1.1" 200'), line
