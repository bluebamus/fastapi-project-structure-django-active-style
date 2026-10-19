"""로그 컨텍스트 필터.

record 에 두 필드를 주입한다.
- appname: 소스 파일 **경로**에서 앱 식별. 로거 이름이 아니라 경로를 쓰는 이유는
  ``app/utils/logs/config.py`` 상단 참고. 산출값은 아래 ``_app_from_path`` 참조.
- classname:
    · 방식 C — LoggerAdapter/extra 로 이미 주입돼 있으면 그대로 존중(오버헤드 0).
    · 방식 A — 없으면 호출 프레임에서 self/cls 를 찾아 클래스명을 자동 추출.
  자유 함수(클래스 없음)는 '-'.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from types import FrameType

# 이 파일은 <저장소루트>/app/utils/logs/filters.py 다. parents[3] 이 저장소 루트.
# 파일을 옮기면 이 계산이 조용히 어긋나므로, tests/utils/test_logs.py 가
# main.py -> "app" 을 단언해 이동을 즉시 잡는다.
_REPO_ROOT = str(Path(__file__).resolve().parents[3]).replace("\\", "/").rstrip("/").lower() + "/"


# 저장소 밖 코드의 출처 — 로거 이름의 첫 조각으로 찾는다. 없으면 ``ext``.
_EXTERNAL_APPS = {
    "celery": "celery",
    "kombu": "celery",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
}


def _app_from_path(pathname: str, name: str = "") -> str:
    """레코드의 출처 라벨(헤더 ``app=``)을 만든다 — 출처 판별은 이 함수 하나다.

    우리 코드(소스 경로로 판별):
        ``<기능명>``  — ``app/features/<name>/**``
        ``core`` · ``celery`` · ``utils`` · ``migrations`` — 해당 하위 시스템
        ``app``  — 그 밖의 **이 저장소 안** 코드(``main.py`` · ``config.py`` · ``tests/**`` 등)
    저장소 밖 코드(로거 이름 ``name`` 으로 판별, ``_EXTERNAL_APPS``):
        ``celery``(celery·kombu) · ``uvicorn`` · ``sqlalchemy`` · ``alembic``, 그 밖은 ``ext``

    예전에는 경로에 ``/app/`` 조각이 있는지로만 판별해서 저장소 루트의 ``main.py``·``config.py``·
    ``migrations/`` 가 ``ext`` 로 빠졌다. 진입점이 서드파티로 분류되면 이 필드로 우리 코드를 거를 수 없다(LOG-2).
    """
    p = pathname.replace("\\", "/")
    if "/features/" in p:
        return p.split("/features/", 1)[1].split("/", 1)[0]
    for seg in ("/app/core/", "/app/celery/", "/app/utils/", "/migrations/"):
        if seg in p:
            return seg.strip("/").rsplit("/", 1)[-1]
    external = _EXTERNAL_APPS.get(name.split(".", 1)[0], "ext")
    # .venv 는 저장소 루트 **안**에 있으므로 루트 판정보다 먼저 걸러야 한다.
    if "/site-packages/" in p or "/dist-packages/" in p:
        return external
    if "/app/" in p:
        return "app"
    return "app" if p.lower().startswith(_REPO_ROOT) else external


def _class_from_stack() -> str:
    """호출 스택에서 logging/이 패키지 프레임을 건너뛰고 첫 사용자 프레임의 클래스명을 찾는다."""
    frame: FrameType | None = sys._getframe(0)
    while frame is not None:
        filename = frame.f_code.co_filename.replace("\\", "/")
        if "/logging/" not in filename and "/utils/logs/" not in filename:
            local_self = frame.f_locals.get("self")
            if local_self is not None:
                return type(local_self).__name__
            local_cls = frame.f_locals.get("cls")
            if isinstance(local_cls, type):
                return local_cls.__name__
            return "-"
        frame = frame.f_back
    return "-"


class ContextFilter(logging.Filter):
    """record 에 appname/classname 을 채운다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "appname", None):
            record.appname = _app_from_path(record.pathname, record.name)
        if not getattr(record, "classname", None):
            record.classname = _class_from_stack()
        return True


# =============================================================================
# 비밀정보 마스킹 (C-5)
# =============================================================================
# SQLAlchemy `echo=False` 는 SQL 로그를 막지만 그건 설정에 기댄 차단이라, 누가
# echo 를 켜거나 드라이버가 예외에 DSN 을 실어 보내면 무너진다. 파이프라인 끝에서
# 한 번 더 지운다.
#
# DSN 마스킹은 config 의 URL 렌더링(`render_as_string(hide_password=True)`)과 같은 의도지만 여기서 다시 구현한다 —
# 로깅 설정은 config 보다 먼저 세워질 수 있어서 import 순서를 얽지 않는다.
# 사용자명이 비어 있는 꼴(`redis://:pw@host`)도 잡는다. 사용자명·비밀번호를 **둘 다** 가린다.
_DSN_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^:/@\s]*):([^@\s]+)@")
_KEYWORD_SECRET = re.compile(
    r"(?i)\b(secret[_-]?key|api[_-]?key|password|passwd|pwd|secret|token)\b"
    r"(\s*[:=]\s*)([\"']?)([^\s\"',;)]+)\3"
)
# `Authorization: Bearer <토큰>` — 키워드 규칙은 `키=값` 꼴만 보므로 헤더 값의 토큰을 놓친다.
_BEARER_TOKEN = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/]+=*")

# traceback 을 미리 렌더할 때 쓰는 기본 포매터. 이 저장소의 포매터(TzFormatter)는
# formatException 을 바꾸지 않으므로 결과가 핸들러의 포매터와 같다.
_EXC_FORMATTER = logging.Formatter()


# 설정에서 모은 비밀값 원문(set_secret_values). 4글자 이상은 어디서든, 짧은 값(주로 계정명)은
# `user=`·`username=` 꼴에서만 가린다 — 짧은 값을 원문 일치로 가리면 일반 단어가 지워진다.
SHORT_SECRET_MIN_LENGTH = 4
_SECRET_VALUES: re.Pattern[str] | None = None
_SHORT_SECRET_VALUES: re.Pattern[str] | None = None


def _alternation(values: list[str]) -> str:
    return "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))


def set_secret_values(values: Iterable[str | None]) -> None:
    """``redact()`` 가 원문으로 가릴 비밀값을 정한다(빈 값 제외). ``configure_logging()`` 이 부른다."""
    global _SECRET_VALUES, _SHORT_SECRET_VALUES
    found = {v for v in values if v and v.strip()}
    long_values = [v for v in found if len(v) >= SHORT_SECRET_MIN_LENGTH]
    short_values = [v for v in found if len(v) < SHORT_SECRET_MIN_LENGTH]
    _SECRET_VALUES = re.compile(_alternation(long_values)) if long_values else None
    _SHORT_SECRET_VALUES = (
        re.compile(rf"(?i)\b(user(?:name)?\s*[:=]\s*[\"']?)(?:{_alternation(short_values)})(?!\w)")
        if short_values
        else None
    )


def redact(text: str) -> str:
    """DSN 자격증명·secret 형태의 값·설정된 비밀값 원문을 ``***`` 로 바꾼다.

    호스트·포트처럼 진단에 필요한 부분은 남긴다 — 통째로 지우면 로그가
    쓸모없어져서 결국 아무도 안 켠다.
    """
    text = _DSN_CREDENTIALS.sub(r"\1***:***@", text)
    text = _BEARER_TOKEN.sub(r"\1***", text)
    text = _KEYWORD_SECRET.sub(r"\1\2\3***\3", text)
    if _SECRET_VALUES is not None:
        text = _SECRET_VALUES.sub("***", text)
    if _SHORT_SECRET_VALUES is not None:
        text = _SHORT_SECRET_VALUES.sub(r"\1***", text)
    return text


class RedactingFilter(logging.Filter):
    """메시지·traceback·stack 에서 비밀정보를 지운다.

    치환이 일어나면 ``args`` 를 비운다 — 포매터가 이미 전개된 문자열을 다시
    전개하려다 깨지지 않게 하기 위해서다.

    예외(``exc_info``)는 여기서 traceback 문자열로 **미리 렌더해 ``exc_text`` 에 고정한 뒤**
    가린다. ``logging.Formatter.format`` 은 ``exc_text`` 가 있으면 다시 만들지 않으므로
    핸들러의 포매터는 가린 본문을 찍는다. 체인 예외(``raise ... from``·암묵 체인)는
    ``formatException`` 이 한 문자열로 펼치므로 함께 가려진다. ``stack_info`` 도 같다.
    예외 타입·파일·줄 번호는 남는다(규칙이 값만 지운다).
    """

    # ponytail: record 마다 getMessage() 를 한 번 더 호출한다(문자열 포매팅 1회분).
    # 로깅이 병목으로 측정되면 레벨/로거 이름으로 사전 선별해 좁힌다.
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 포매팅 실패는 로깅이 알아서 보고한다
            return True
        if redact(message) != message:
            # 비밀값이 인자 하나 안에 있으면 그 인자만 가려 args 모양을 지킨다 — uvicorn AccessFormatter 는
            # 접속 줄의 args 5개를 풀어 요청 라인을 만든다(R-804). 틀과 인자에 걸쳐 있어
            # (`password=%s`) 인자만으로 못 가리면 전개한 문자열을 가리고 args 를 비운다.
            if isinstance(record.args, tuple):
                record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
            partial = record.getMessage()
            if redact(partial) != partial:
                record.msg = redact(message)
                record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = _EXC_FORMATTER.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def redact_handlers(*loggers: logging.Logger) -> None:
    """로거에 **이미 붙어 있는** 핸들러에 ``RedactingFilter`` 를 단다(멱등).

    우리 dictConfig 밖에서 만들어진 핸들러용이다 — ``uvicorn main:app`` 이 앱 import 전에
    세운 uvicorn 기본 핸들러, Celery 워커가 root 를 가로채며 붙인 핸들러. 이 핸들러들은
    ``propagate=False`` 이거나 root 를 대체해서 우리 핸들러의 필터를 거치지 않는다.
    """
    for logger in loggers:
        for handler in logger.handlers:
            if not any(isinstance(f, RedactingFilter) for f in handler.filters):
                handler.addFilter(RedactingFilter())


class SQLNoiseFilter(logging.Filter):
    """SQL·드라이버 로거의 DEBUG·INFO 를 차단한다 (계획서 §8, ADR-004).

    ## 왜 레벨이 아니라 필터인가

    이 저장소는 **앱별 로거를 등록하지 않는다**(`config.py` 참고). 핸들러는 root 에만
    붙고 레벨도 root 하나다. `loggers` 항목을 추가하면 "새 기능 추가 시 로깅 설정에
    손댈 곳이 0" 이라는 성질이 깨진다. 필터는 그 설계를 건드리지 않고 목적을 이룬다.

    ## 왜 차단해야 하는가

    SQLAlchemy 의 `echo` 계열 로그는 **SQL 본문과 바인딩된 파라미터를 그대로** 찍는다.
    거기에는 사용자 식별자·검색어·이메일이 들어 있다. `RedactingFilter` 는 알려진
    키워드(password 등)만 마스킹하므로 SQL 전문 노출을 막지 못한다 — 둘은 역할이
    다르고 둘 다 필요하다.

    ## WARNING 이상은 통과시킨다

    "SQL 로그를 전부 끈다" 가 아니다. 커넥션 풀 고갈, 재연결 실패, 드라이버 경고는
    장애 진단에 반드시 필요하다. 차단 대상은 **정상 동작의 소음**(DEBUG·INFO)뿐이다.

    ## opt-in

    `LOG_SQL_ECHO_ENABLED=true` 로 켤 수 있으나 development/test 에서만 유효하다.
    staging/production 에서 켜면 기동이 실패한다(`config.validate_deployment_safety`).
    환경 제한이 없으면 "잠깐 켜둔" 설정이 운영에 그대로 남는다.
    """

    # 소음을 내는 로거들. 접두사 일치로 하위 로거까지 포함한다
    # (`sqlalchemy.engine.Engine`, `aiomysql.cursors` 등).
    NOISY_PREFIXES = ("sqlalchemy", "aiomysql", "aiosqlite", "asyncmy", "pymysql", "alembic.ddl")

    def __init__(self, name: str = "", *, allow_sql_echo: bool | None = None) -> None:
        super().__init__(name)
        if allow_sql_echo is None:
            from config import app_settings, log_settings

            # 설정이 켜져 있어도 운영 환경이면 무시한다. 이중 방어 — 배포 검증이
            # 먼저 막지만, 검증을 우회하는 경로가 생겨도 여기서 한 번 더 걸린다.
            allow_sql_echo = bool(getattr(log_settings, "LOG_SQL_ECHO_ENABLED", False)) and getattr(
                app_settings, "ENV", "development"
            ) in ("development", "test")
        self._allow_sql_echo = allow_sql_echo

    def filter(self, record: logging.LogRecord) -> bool:
        if self._allow_sql_echo:
            return True
        if record.levelno >= logging.WARNING:
            return True
        return not record.name.startswith(self.NOISY_PREFIXES)
