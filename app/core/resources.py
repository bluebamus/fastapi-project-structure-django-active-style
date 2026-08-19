"""애플리케이션 자원의 수명주기 관리 (계획서 §8, ADR-001·ADR-007).

## 왜 이 파일이 필요한가

정리 코드가 `try/finally` 안에 늘어서 있으면 **최선의 경우에만** 동작한다. 실제로
이 저장소의 `dispose_engine()` 은 writer → replica → background 를 순차로 부르는데,
앞의 dispose 가 예외를 내면 **뒤의 두 개는 실행되지 않는다.** 커넥션이 남고, 증상은
한참 뒤 "재시작이 느려짐"·"커넥션 소진" 으로만 나타난다.

여기서 고치는 것은 세 가지다.

1. **등록은 start 이전에.** fallible 한 start 뒤에 cleanup 을 등록하면 start 가
   실패했을 때 등록 자체가 일어나지 않는다. 그래서 `acquire()` 는 정리 함수를 **먼저**
   등록하고 그다음 start 를 부른다. start 가 실패해도 이미 등록돼 있으므로 회수된다.
2. **부분 실패 내성.** 정리 하나가 예외를 내도 나머지를 계속 실행한다. 정리는
   "가능한 만큼 회수" 가 목표이지 "첫 실패에서 멈추기" 가 아니다.
3. **단일 deadline.** 단계마다 timeout 을 따로 두면 최악의 경우 그 **합**이 전체
   예산을 넘어, 오케스트레이터의 강제 종료(SIGKILL)에 걸린다. 그러면 정리가 아예
   안 된 상태로 죽는다. 그래서 하나의 monotonic deadline 에서 남은 시간을 배분한다.

## 정리 순서

등록의 **역순**이다. 나중에 만든 것이 먼저 만든 것에 의존하기 때문이다 —
background task 는 DB 엔진을 쓰고, 로깅은 그 둘의 종료 메시지를 받아야 한다.

    등록: 로깅 → 엔진 → 백그라운드 태스크
    정리: 백그라운드 태스크 → 엔진 → 로깅

## 쓰는 법

    resources = ResourceManager(deadline_seconds=20.0)
    resources.register("background-tasks", tasks.drain, budget=5.0)
    resources.register("db-engines", dispose_engine, budget=10.0)
    ...
    await resources.close()   # 역순 정리, 부분 실패 내성, 단일 deadline

`close()` 는 **멱등**이다. 두 번 불러도 정리는 한 번만 일어난다 — lifespan 이
예외 경로와 정상 경로 양쪽에서 부를 수 있어야 하기 때문이다.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.utils.logs import get_logger

__all__ = ["ManagedResource", "ResourceManager"]

logger = get_logger("resources")

# 전체 종료 예산. 오케스트레이터(k8s terminationGracePeriodSeconds 등)가 주는 시간보다
# 짧아야 한다 — 우리가 먼저 끝내야 정리가 완료된 상태로 죽는다.
DEFAULT_DEADLINE_SECONDS = 20.0

# 마지막 자원까지 최소한의 시간을 남겨두기 위한 예비분. 앞선 자원이 예산을 다 써도
# 뒤의 자원이 "0초" 를 받지 않게 한다.
CLEANUP_RESERVE_SECONDS = 1.0


@dataclass(slots=True)
class ManagedResource:
    """관리 대상 자원 하나.

    Attributes:
        name: 로그에 남는 이름. 실패했을 때 **무엇이** 실패했는지 알려면 필요하다.
        cleanup: 정리 코루틴 함수. 인자 없이 호출된다.
        budget: 이 자원에 할당할 최대 시간(초). 남은 deadline 과 비교해 작은 쪽을 쓴다.
    """

    name: str
    cleanup: Callable[[], Awaitable[None]]
    budget: float


@dataclass(slots=True)
class ResourceManager:
    """등록 역순으로, 부분 실패를 견디며, 단일 deadline 안에서 정리한다."""

    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS
    _resources: list[ManagedResource] = field(default_factory=list)
    _closed: bool = False

    # ------------------------------------------------------------------ 등록

    def register(
        self,
        name: str,
        cleanup: Callable[[], Awaitable[None]],
        *,
        budget: float,
    ) -> None:
        """정리 함수를 등록한다. 정리는 등록의 역순으로 실행된다."""
        if self._closed:
            raise RuntimeError(f"이미 종료된 ResourceManager 에 '{name}' 을 등록할 수 없습니다.")
        self._resources.append(ManagedResource(name=name, cleanup=cleanup, budget=budget))

    async def acquire(
        self,
        name: str,
        start: Callable[[], Awaitable[None]],
        cleanup: Callable[[], Awaitable[None]],
        *,
        budget: float,
    ) -> None:
        """자원을 확보한다. **정리를 먼저 등록한 뒤** start 를 부른다.

        순서가 핵심이다. start 뒤에 등록하면 start 가 실패했을 때 등록이 일어나지
        않아, 절반쯤 확보된 자원이 회수되지 않는다. 정리 함수는 "아직 start 하지
        않은 상태" 에서 호출돼도 안전해야 한다(멱등).

        Raises:
            Exception: start 가 낸 예외를 그대로 전파한다. 등록은 이미 끝나 있으므로
                호출자가 `close()` 를 부르면 회수된다.
        """
        self.register(name, cleanup, budget=budget)
        await start()

    @property
    def names(self) -> list[str]:
        """등록된 자원 이름(등록 순)."""
        return [resource.name for resource in self._resources]

    # ------------------------------------------------------------------ 정리

    async def close(self) -> None:
        """등록 역순으로 정리한다. 멱등이며, 하나가 실패해도 나머지를 계속한다."""
        if self._closed:
            return
        self._closed = True

        if not self._resources:
            return

        started = time.monotonic()
        failures: list[str] = []

        for resource in reversed(self._resources):
            remaining = self.deadline_seconds - (time.monotonic() - started)
            if remaining <= 0:
                # 예산이 끝났다. 남은 자원은 **건너뛰지 않고** 최소 예비분으로 시도한다 —
                # 아무것도 안 하는 것보다 짧게라도 시도하는 편이 회수 확률이 높다.
                remaining = CLEANUP_RESERVE_SECONDS
            allotted = min(resource.budget, remaining)

            try:
                async with asyncio.timeout(allotted):
                    await resource.cleanup()
            except TimeoutError:
                failures.append(resource.name)
                logger.warning(
                    "[resources] '%s' 정리가 %.1fs 안에 끝나지 않았습니다 — 다음으로 넘어갑니다.",
                    resource.name,
                    allotted,
                )
            except Exception as error:
                # 정리 실패는 기록하고 넘어간다. 여기서 멈추면 뒤의 자원이 전부 샌다.
                # 예외 원문은 남기지 않는다(C-4) — 타입과 자원 이름이면 추적에 충분하다.
                failures.append(resource.name)
                logger.warning(
                    "[resources] '%s' 정리 실패 error_type=%s — 다음으로 넘어갑니다.",
                    resource.name,
                    type(error).__name__,
                )
            else:
                logger.debug("[resources] '%s' 정리 완료", resource.name)

        elapsed = time.monotonic() - started
        if failures:
            logger.warning(
                "[resources] 정리 완료 — %d/%d 실패(%s), %.1fs 소요",
                len(failures),
                len(self._resources),
                ", ".join(failures),
                elapsed,
            )
        else:
            logger.info(
                "[resources] 정리 완료 — %d개 전부 회수, %.1fs 소요",
                len(self._resources),
                elapsed,
            )
