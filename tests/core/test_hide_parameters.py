"""DB 오류 로그·예외 문자열에 바인드 값이 실리지 않는다 (security-ops-hardening ADR-001).

SQLAlchemy 예외의 ``str()`` 에는 기본으로 SQL 과 **바인드 값**(이메일·비밀번호 해시·토큰)이
그대로 들어간다. 값은 키워드 형태가 아니라 RedactingFilter 로는 지울 수 없어서, 엔진 옵션
``hide_parameters=True`` 로 근원에서 뺀다. 모든 엔진은 ``ENGINE_SAFETY_OPTIONS`` 를 펼친다.
"""

import ast
import io
import logging
from logging.config import dictConfig
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import URL
from sqlalchemy.exc import IntegrityError

from app.core.db import session as db_session
from app.core.db.session import ENGINE_SAFETY_OPTIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_EMAIL = "leak-probe-7f3a@example.com"
SECRET_HASH = "$argon2id$v=19$leak-probe-hash-91c2"
HIDDEN_MARK = "hidden due to hide_parameters=True"

_metadata = sa.MetaData()
_accounts = sa.Table(
    "accounts",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("email", sa.String(100), unique=True, nullable=False),
    sa.Column("hashed_password", sa.String(200), nullable=False),
)


def _integrity_error() -> IntegrityError:
    """운영과 같은 옵션으로 만든 SQLite 엔진에서 고유 제약 위반을 일으킨다."""
    engine = sa.create_engine("sqlite://", **ENGINE_SAFETY_OPTIONS)
    try:
        with engine.begin() as conn:
            _metadata.create_all(conn)
            row = {"email": SECRET_EMAIL, "hashed_password": SECRET_HASH}
            conn.execute(_accounts.insert(), row)
            with pytest.raises(IntegrityError) as caught:
                conn.execute(_accounts.insert(), row)
        return caught.value
    finally:
        engine.dispose()


def test_integrity_error_text_keeps_sql_but_hides_bound_values():
    text = str(_integrity_error())

    assert SECRET_EMAIL not in text and SECRET_HASH not in text, text
    assert "INSERT INTO accounts" in text  # 진단용 SQL 문은 남는다
    assert HIDDEN_MARK in text


def _app_engines() -> list[tuple[str, sa.Engine]]:
    read_probe = db_session._create_read_engine(
        URL.create("mysql+aiomysql", username="u", host="replica", database="d")
    )
    return [
        ("writer", db_session.engine.sync_engine),
        ("background", db_session.background_engine.sync_engine),
        ("reader(factory)", read_probe.sync_engine),
        *((f"reader#{i}", e.sync_engine) for i, e in enumerate(db_session.read_engines)),
    ]


@pytest.mark.parametrize(("name", "engine"), [pytest.param(n, e, id=n) for n, e in _app_engines()])
def test_every_app_engine_hides_parameters(name, engine):
    """엔진 객체 계약 — 연결 없이 속성만 본다."""
    assert engine.hide_parameters is True, name


_ENGINE_FACTORIES = {"create_engine", "create_async_engine", "engine_from_config"}


def _engine_construction_sites() -> tuple[list[str], list[str]]:
    """(모든 엔진 생성 호출 위치, 그중 정본 옵션을 펼치지 않은 위치)."""
    seen, offenders = [], []
    sources = [*(REPO_ROOT / "app").rglob("*.py"), *(REPO_ROOT / "migrations").rglob("*.py")]
    sources += [*(REPO_ROOT / "scripts").rglob("*.py")]
    for path in sources:
        if "tests" in path.relative_to(REPO_ROOT).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _ENGINE_FACTORIES:
                continue
            spreads = any(
                kw.arg is None
                and isinstance(kw.value, ast.Name)
                and kw.value.id == "ENGINE_SAFETY_OPTIONS"
                for kw in node.keywords
            )
            where = f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}"
            seen.append(where)
            if not spreads:
                offenders.append(where)
    return seen, offenders


def test_every_engine_construction_site_spreads_the_safety_options():
    """새 엔진 생성 지점(Alembic 포함)이 정본 옵션을 빠뜨리면 여기서 멈춘다."""
    assert _engine_construction_sites()[1] == []


def test_construction_site_guard_sees_real_sites():
    """대조군 — 검사가 아무 호출도 못 보는 헛통과가 아니다(writer·reader·background·Alembic)."""
    files = sorted(site.split(":")[0] for site in _engine_construction_sites()[0])
    assert files == ["app/core/db/session.py"] * 3 + ["migrations/env.py"]


def test_logger_exception_through_the_app_pipeline_has_no_bound_values(monkeypatch):
    """운영 로그 구성(dictConfig)으로 ``logger.exception`` 해도 값이 나가지 않는다."""
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config.app_settings, "ENV", "development", raising=False)
    cfg = logs_config.build_dictconfig()
    cfg["loggers"] = {"hide-params-probe": {**cfg.pop("root"), "level": "DEBUG"}}
    cfg["loggers"]["hide-params-probe"]["propagate"] = False
    probe = logging.getLogger("hide-params-probe")
    saved_root = logging.getLogger().handlers[:]
    try:
        dictConfig(cfg)
        buf = io.StringIO()
        for handler in probe.handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(buf)
        error = _integrity_error()
        try:
            raise error
        except IntegrityError:
            probe.exception("insert failed")
    finally:
        for handler in probe.handlers:
            handler.close()
        probe.handlers.clear()
        logging.getLogger().handlers[:] = saved_root

    out = buf.getvalue()
    assert "insert failed" in out and "IntegrityError" in out
    assert SECRET_EMAIL not in out and SECRET_HASH not in out, out
    assert HIDDEN_MARK in out
