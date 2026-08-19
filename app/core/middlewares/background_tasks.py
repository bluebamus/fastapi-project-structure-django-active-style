"""요청-밖 fire-and-forget 태스크의 상한(백프레셔) + 종료 시 drain 관리.

미들웨어(접속로그 저장)가 응답 후 던지는 백그라운드 태스크를 관리한다.

- **백프레셔**: 동시 실행 태스크를 ``max_concurrent`` 로 제한한다. 초과분은
  드롭하고 ``dropped`` 로 집계한다(요청 처리를 블로킹하지 않기 위해, 비핵심
  로그는 막지 않고 버린다). 상한이 없으면 고부하 시 태스크·커넥션이 무제한
  증가해 백그라운드 풀(pool_timeout) 대기가 누적된다.
- **Drain**: 앱 종료(lifespan shutdown)에서 in-flight 태스크를 정리한다.

## drain 이 왜 이 순서인가 (계획서 §8, ADR-002)

이전 구현은 timeout 후 미완료 태스크를 **경고만 하고 버렸다**. 버린 태스크는
사라지지 않는다 — 여전히 살아서 다음 순간 ``dispose_engine()`` 이 닫아버린
커넥션을 쓰려다 실패한다. 그 실패 예외는 아무도 읽지 않아 인터프리터 종료 시
"Task exception was never retrieved" 로만 남는다. 그래서 순서를 못박는다.

1. **admission 종료** — 더 이상 받지 않는다. 이걸 먼저 하지 않으면 drain 중에
   새 태스크가 들어와 종료가 끝나지 않는다.
2. **timeout 까지 대기** — 정상적으로 끝날 기회를 준다.
3. **남은 것 cancel** — 버리지 않고 명시적으로 취소한다.
4. **cancel 한 것까지 다시 await** — 취소가 **완료될 때까지** 기다린다. cancel 은
   요청일 뿐이라, await 하지 않으면 태스크는 아직 정리 중이다.
5. **예외 소비 + 추적 집합 비우기** — 완료된 태스크의 예외를 읽어 "never
   retrieved" 경고를 없앤다. 예외 내용은 로그 타입까지만 남긴다.

전역 싱글턴 ``access_log_tasks`` 를 미들웨어(spawn)와 main lifespan(drain)이
공유한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.utils.logs import get_logger

logger = get_logger("background_tasks")

# 동시 백그라운드 로그 태스크 상한 및 종료 drain 타임아웃(초).
# 정상 트래픽보다 넉넉하되 무제한 증가를 막는 안전판.
MAX_CONCURRENT_LOG_TASKS = 256
DRAIN_TIMEOUT_SECONDS = 5.0


class BackgroundTaskRunner:
    """동시 실행 상한과 종료 drain 을 갖춘 fire-and-forget 태스크 러너."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_LOG_TASKS) -> None:
        self._max = max_concurrent
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False
        self.dropped = 0
        self.rejected_after_close = 0

    @property
    def active(self) -> int:
        """추적 중인 in-flight 태스크 수."""
        return len(self._tasks)

    @property
    def closed(self) -> bool:
        """더 이상 태스크를 받지 않는 상태인가."""
        return self._closed

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> bool:
        """코루틴을 백그라운드 태스크로 실행한다.

        종료가 시작됐거나 상한에 도달하면 실행하지 않고 코루틴을 닫는다.

        Returns:
            수락하여 태스크를 만들었으면 True, 거부했으면 False.
        """
        if self._closed:
            # 종료 중에 들어온 요청. 받으면 drain 이 끝나지 않는다.
            self.rejected_after_close += 1
            coro.close()  # "coroutine was never awaited" 경고 방지
            return False

        if len(self._tasks) >= self._max:
            self.dropped += 1
            coro.close()
            logger.warning(
                "백그라운드 태스크 상한(%d) 초과 — 드롭(누적 %d)",
                self._max,
                self.dropped,
            )
            return False

        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def close_admission(self) -> None:
        """더 이상 새 태스크를 받지 않는다(멱등)."""
        self._closed = True

    async def drain(self, timeout: float = DRAIN_TIMEOUT_SECONDS) -> None:
        """in-flight 태스크를 정리한다. 호출 후 추적 집합은 비어 있다."""
        # admission 을 먼저 닫는다 — 아래에서 기다리는 동안 새 태스크가 들어오면
        # 종료가 끝나지 않는다.
        self.close_admission()

        pending = set(self._tasks)
        if not pending:
            return

        logger.info("백그라운드 태스크 drain 시작 — %d건 대기", len(pending))
        done, still_pending = await asyncio.wait(pending, timeout=timeout)

        if still_pending:
            logger.warning(
                "drain 타임아웃(%.1fs) — 미완료 %d건을 취소합니다.", timeout, len(still_pending)
            )
            for task in still_pending:
                task.cancel()
            # cancel 은 "요청" 일 뿐이다. 취소가 **완료될 때까지** 기다리지 않으면
            # 태스크는 아직 살아 있고, 곧 닫힐 엔진을 건드린다.
            cancelled, _ = await asyncio.wait(still_pending)
            done |= cancelled

        self._consume_exceptions(done)
        self._tasks.clear()
        logger.info("백그라운드 태스크 drain 완료 — %d건 정리", len(done))

    @staticmethod
    def _consume_exceptions(tasks: set[asyncio.Task[Any]]) -> None:
        """완료된 태스크의 예외를 읽어 "never retrieved" 경고를 없앤다.

        예외 **원문은 남기지 않는다**. 백그라운드 태스크는 DB 를 만지므로 예외에
        DSN·쿼리 조각이 실려올 수 있다(C-4). 타입이면 추적에 충분하다.
        """
        for task in tasks:
            if task.cancelled():
                continue
            error = task.exception()
            if error is not None:
                logger.warning("백그라운드 태스크 실패 error_type=%s", type(error).__name__)


# 미들웨어(spawn)와 lifespan(drain)이 공유하는 전역 싱글턴.
access_log_tasks = BackgroundTaskRunner()
