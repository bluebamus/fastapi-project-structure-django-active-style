"""자원 관리자 계약 (INV-1·INV-2·INV-11, Phase 1-R2).

정리 코드는 **최선의 경우에만 동작하기 쉽다**. 정상 종료만 테스트하면 그 사실이
드러나지 않는다 — 정상 경로는 어떤 구현이든 통과하기 때문이다. 그래서 여기서 보는
것은 전부 **나쁜 경로**다: 정리 하나가 예외를 낼 때, startup 이 중간에 실패할 때,
자원 하나가 응답하지 않을 때.

실제로 이 저장소의 `dispose_engine()` 은 앞의 dispose 가 실패하면 뒤의 엔진을
회수하지 않는 상태였다. 그 구조를 여기서 못박는다.
"""

import asyncio
import time

import pytest

from app.core.resources import ResourceManager


def _recorder():
    """호출 순서를 기록하는 리스트와 정리 함수 팩토리."""
    calls: list[str] = []

    def cleanup(name: str, *, fail: bool = False, delay: float = 0.0):
        async def _cleanup() -> None:
            if delay:
                await asyncio.sleep(delay)
            calls.append(name)
            if fail:
                raise RuntimeError(f"{name} 정리 실패")

        return _cleanup

    return calls, cleanup


# ------------------------------------------------------------------ INV-1


async def test_cleanup_runs_in_reverse_registration_order():
    """나중에 만든 것이 먼저 만든 것에 의존하므로 역순이어야 한다."""
    calls, cleanup = _recorder()
    manager = ResourceManager()
    manager.register("logging", cleanup("logging"), budget=1.0)
    manager.register("engines", cleanup("engines"), budget=1.0)
    manager.register("tasks", cleanup("tasks"), budget=1.0)

    await manager.close()

    assert calls == ["tasks", "engines", "logging"]


async def test_one_failing_cleanup_does_not_stop_the_rest():
    """정리는 '가능한 만큼 회수' 가 목표다 — 첫 실패에서 멈추면 뒤가 전부 샌다."""
    calls, cleanup = _recorder()
    manager = ResourceManager()
    manager.register("logging", cleanup("logging"), budget=1.0)
    manager.register("engines", cleanup("engines", fail=True), budget=1.0)
    manager.register("tasks", cleanup("tasks"), budget=1.0)

    await manager.close()

    assert calls == ["tasks", "engines", "logging"], "실패 이후 자원이 정리되지 않았습니다."


async def test_close_does_not_raise_when_every_cleanup_fails():
    """종료 경로가 예외를 던지면 lifespan 이 그 위에서 또 깨진다."""
    _, cleanup = _recorder()
    manager = ResourceManager()
    manager.register("a", cleanup("a", fail=True), budget=1.0)
    manager.register("b", cleanup("b", fail=True), budget=1.0)

    await manager.close()  # 예외가 새어나오면 이 테스트가 실패한다


async def test_close_is_idempotent():
    """lifespan 은 정상·예외 경로 양쪽에서 close 를 부를 수 있어야 한다."""
    calls, cleanup = _recorder()
    manager = ResourceManager()
    manager.register("a", cleanup("a"), budget=1.0)

    await manager.close()
    await manager.close()

    assert calls == ["a"], "두 번째 close 에서 정리가 다시 실행됐습니다."


async def test_registering_after_close_is_rejected():
    """이미 정리된 관리자에 등록하면 그 자원은 영원히 회수되지 않는다."""
    manager = ResourceManager()
    await manager.close()

    with pytest.raises(RuntimeError):
        manager.register("late", lambda: asyncio.sleep(0), budget=1.0)


# ------------------------------------------------------------------ INV-2


async def test_acquire_registers_cleanup_before_start():
    """start 가 실패해도 회수된다 — 등록이 start **앞에** 있기 때문이다."""
    calls, cleanup = _recorder()
    manager = ResourceManager()

    async def failing_start() -> None:
        raise RuntimeError("start 실패")

    with pytest.raises(RuntimeError):
        await manager.acquire("engines", failing_start, cleanup("engines"), budget=1.0)

    await manager.close()

    assert calls == ["engines"], "start 실패한 자원이 회수되지 않았습니다."


async def test_startup_failure_cleans_up_earlier_resources():
    """두 번째 자원 확보가 실패해도 첫 자원은 회수된다."""
    calls, cleanup = _recorder()
    manager = ResourceManager()

    async def ok_start() -> None:
        return None

    async def failing_start() -> None:
        raise RuntimeError("두 번째 자원 실패")

    await manager.acquire("logging", ok_start, cleanup("logging"), budget=1.0)
    with pytest.raises(RuntimeError):
        await manager.acquire("engines", failing_start, cleanup("engines"), budget=1.0)

    await manager.close()

    assert calls == ["engines", "logging"]


# ------------------------------------------------------------------ INV-11


async def test_total_shutdown_stays_within_the_single_deadline():
    """단계 timeout 의 **합**이 아니라 하나의 deadline 안에서 배분한다.

    각 자원이 3초 예산을 갖지만 전체 deadline 은 1초다. 합(9초)을 쓰면 오케스트레이터
    강제 종료에 걸려 정리가 아예 안 된 상태로 죽는다.
    """
    _, cleanup = _recorder()
    manager = ResourceManager(deadline_seconds=1.0)
    for name in ("a", "b", "c"):
        manager.register(name, cleanup(name, delay=5.0), budget=3.0)

    started = time.monotonic()
    await manager.close()
    elapsed = time.monotonic() - started

    assert elapsed < 4.0, f"단일 deadline 이 지켜지지 않았습니다: {elapsed:.1f}s"


async def test_slow_resource_does_not_starve_the_next_one():
    """앞의 자원이 예산을 다 써도 뒤의 자원은 시도된다."""
    calls, cleanup = _recorder()
    manager = ResourceManager(deadline_seconds=0.5)
    manager.register("last", cleanup("last"), budget=1.0)
    manager.register("slow", cleanup("slow", delay=2.0), budget=1.0)

    await manager.close()

    assert "last" in calls, "예산 소진 후 남은 자원이 아예 시도되지 않았습니다."


async def test_names_reports_registration_order():
    manager = ResourceManager()
    manager.register("a", lambda: asyncio.sleep(0), budget=1.0)
    manager.register("b", lambda: asyncio.sleep(0), budget=1.0)

    assert manager.names == ["a", "b"]
