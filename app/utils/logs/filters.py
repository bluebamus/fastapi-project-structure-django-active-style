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
from pathlib import Path
from types import FrameType

# 이 파일은 <저장소루트>/app/utils/logs/filters.py 다. parents[3] 이 저장소 루트.
# 파일을 옮기면 이 계산이 조용히 어긋나므로, tests/utils/test_logs.py 가
# main.py -> "app" 을 단언해 이동을 즉시 잡는다.
_REPO_ROOT = str(Path(__file__).resolve().parents[3]).replace("\\", "/").rstrip("/").lower() + "/"


def _app_from_path(pathname: str) -> str:
    """소스 경로에서 앱 라벨을 만든다.

    반환값:
        ``<기능명>``  — ``app/features/<name>/**``
        ``core`` · ``celery`` · ``utils`` · ``migrations`` — 해당 하위 시스템
        ``app``  — 그 밖의 **이 저장소 안** 코드(``main.py`` · ``config.py`` · ``tests/**`` 등)
        ``ext``  — **저장소 밖** 코드(설치된 서드파티 패키지)

    ``ext`` 는 "우리 코드가 아님"을 뜻한다. 예전에는 경로에 ``/app/`` 조각이 있는지로만
    판별해서 저장소 루트의 ``main.py``·``config.py``·``migrations/`` 가 ``ext`` 로 빠졌다.
    진입점이 서드파티로 분류되면 이 필드로 우리 코드를 거를 수 없다(LOG-2).
    """
    p = pathname.replace("\\", "/")
    if "/features/" in p:
        return p.split("/features/", 1)[1].split("/", 1)[0]
    for seg in ("/app/core/", "/app/celery/", "/app/utils/", "/migrations/"):
        if seg in p:
            return seg.strip("/").rsplit("/", 1)[-1]
    # .venv 는 저장소 루트 **안**에 있으므로 루트 판정보다 먼저 걸러야 한다.
    if "/site-packages/" in p or "/dist-packages/" in p:
        return "ext"
    if "/app/" in p:
        return "app"
    return "app" if p.lower().startswith(_REPO_ROOT) else "ext"


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
            record.appname = _app_from_path(record.pathname)
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
# DSN 마스킹 규칙은 config.mask_dsn 과 같은 의도지만 여기서 다시 구현한다 —
# 로깅 설정은 config 보다 먼저 세워질 수 있어서 import 순서를 얽지 않는다.
_DSN_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^:/@\s]+):([^@\s]+)@")
_KEYWORD_SECRET = re.compile(
    r"(?i)\b(secret[_-]?key|api[_-]?key|password|passwd|pwd|secret|token)\b"
    r"(\s*[:=]\s*)([\"']?)([^\s\"',;)]+)\3"
)


def redact(text: str) -> str:
    """DSN 자격증명과 secret 형태의 값을 ``***`` 로 바꾼다.

    호스트·포트·사용자명처럼 진단에 필요한 부분은 남긴다 — 통째로 지우면 로그가
    쓸모없어져서 결국 아무도 안 켠다.
    """
    text = _DSN_CREDENTIALS.sub(r"\1\2:***@", text)
    return _KEYWORD_SECRET.sub(r"\1\2\3***\3", text)


class RedactingFilter(logging.Filter):
    """포매팅된 메시지에서 비밀정보를 지운다.

    치환이 일어나면 ``args`` 를 비운다 — 포매터가 이미 전개된 문자열을 다시
    전개하려다 깨지지 않게 하기 위해서다.
    """

    # ponytail: record 마다 getMessage() 를 한 번 더 호출한다(문자열 포매팅 1회분).
    # 로깅이 병목으로 측정되면 레벨/로거 이름으로 사전 선별해 좁힌다.
    # exc_info 로 실려오는 traceback 본문은 검사하지 않는다 — 필요해지면 포매터
    # 단계에서 exc_text 를 한 번 더 통과시킨다.
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 포매팅 실패는 로깅이 알아서 보고한다
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
