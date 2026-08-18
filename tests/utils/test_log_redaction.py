"""로그 비밀정보 마스킹 (C-5, residual-risk R-007).

지금은 SQLAlchemy `echo=False` 라 SQL 이 로그로 나가지 않는다. 그건 **설정**에
기댄 차단이라 누가 echo 를 켜는 순간 무너진다. 구조적으로 막기 위해 로깅 파이프라인
자체에서 DSN 자격증명과 secret 형태의 값을 지운다.
"""

import logging
from pathlib import Path

import pytest

from app.utils.logs.filters import RedactingFilter

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
