"""날짜 + 크기로 교체하고 보관 일수가 지난 파일을 지우는 파일 핸들러 (logging-overhaul L6, ADR-002).

- 매일 **UTC 자정**에 ``app.log`` → ``app.log.2026-10-19`` (파일 로그는 staging/production 에만 있고
  그 줄의 시각도 UTC 다 — 파일 이름의 날짜와 줄의 날짜가 같아진다).
- 하루 안에서 ``max_bytes`` 를 넘으면 그날 이름의 다음 빈 번호로 옮긴다:
  ``app.log.2026-10-19`` → ``.1`` → ``.2`` … (번호가 클수록 나중 조각).
- 교체할 때마다 ``retention_days`` 보다 오래된 ``app.log.<날짜>[.<번호>]`` 를 지운다.
  정확히 N일 전은 남는다. ``0`` 이면 지우지 않는다.

한 파일을 **한 프로세스**가 쓴다는 전제다. 여러 프로세스가 같은 파일을 회전시키면 안전하지 않다
(uvicorn ``--workers`` 2 이상, Celery prefork 동시성 2 이상) — README "로깅" 의 다중 워커 주의를 따른다.
"""

from __future__ import annotations

import os
import re
import time
from datetime import UTC, datetime, timedelta
from logging import LogRecord
from logging.handlers import TimedRotatingFileHandler


class DailyRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename: str,
        max_bytes: int = 0,
        retention_days: int = 0,
        encoding: str = "utf-8",
    ) -> None:
        # delay=True — 쓰기 전에는 파일을 열지 않는다. 이 프로세스가 쓰지 않을 파일을 붙잡지 않는다.
        super().__init__(filename, when="midnight", utc=True, encoding=encoding, delay=True)
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        directory, base = os.path.split(self.baseFilename)
        self._directory = directory
        self._history = re.compile(re.escape(base) + r"\.(\d{4}-\d{2}-\d{2})(?:\.\d+)?")

    def shouldRollover(self, record: LogRecord) -> bool:
        if super().shouldRollover(record):
            return True
        if self.max_bytes <= 0:
            return False
        if self.stream is None:
            self.stream = self._open()
        position = self.stream.tell()
        return bool(position) and position + len(self.format(record)) + 1 >= self.max_bytes

    def doRollover(self) -> None:
        now = int(time.time())
        if now >= self.rolloverAt:  # 자정이 지났다 — 지난 구간의 날짜로 옮긴다
            day = time.strftime("%Y-%m-%d", time.gmtime(self.rolloverAt - self.interval))
            self.rolloverAt = self.computeRollover(now)
        else:  # 하루 안 크기 초과
            day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        if os.path.exists(self.baseFilename):
            target, number = f"{self.baseFilename}.{day}", 0
            while os.path.exists(target):
                number += 1
                target = f"{self.baseFilename}.{day}.{number}"
            self.rotate(self.baseFilename, target)
        self._delete_expired(now)

    def _delete_expired(self, now: int) -> None:
        if self.retention_days <= 0:
            return
        cutoff = (
            datetime.fromtimestamp(now, UTC).date() - timedelta(days=self.retention_days)
        ).isoformat()
        for name in os.listdir(self._directory):
            match = self._history.fullmatch(name)
            if match and match[1] < cutoff:
                os.remove(os.path.join(self._directory, name))
