"""BackgroundTaskRunner 회귀 테스트 (검수 W1/REQ-009).

미들웨어 접속로그 저장을 fire-and-forget 로 던지되,
- 동시 실행 태스크 수에 상한을 두어(백프레셔) 고부하 시 무제한 증가를 막고,
- 앱 종료 시 in-flight 태스크를 drain 하여 마지막 로그 유실/엔진 경합을 줄인다.
"""

import asyncio

from app.core.middlewares.background_tasks import BackgroundTaskRunner


async def test_backpressure_drops_tasks_over_capacity() -> None:
    runner = BackgroundTaskRunner(max_concurrent=2)
    gate = asyncio.Event()

    async def blocked() -> None:
        await gate.wait()

    accepted = [runner.spawn(blocked()) for _ in range(5)]

    assert accepted.count(True) == 2, "상한(2)까지만 수락해야 함"
    assert runner.dropped == 3, "초과분 3건은 드롭·집계되어야 함"

    gate.set()
    await runner.drain(timeout=1.0)


async def test_drain_waits_for_inflight_tasks() -> None:
    runner = BackgroundTaskRunner(max_concurrent=10)
    done: list[int] = []

    async def work(i: int) -> None:
        await asyncio.sleep(0.01)
        done.append(i)

    for i in range(5):
        assert runner.spawn(work(i)) is True

    await runner.drain(timeout=2.0)

    assert sorted(done) == [0, 1, 2, 3, 4], "drain 은 모든 in-flight 태스크 완료를 기다려야 함"


async def test_completed_tasks_are_not_retained() -> None:
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def quick() -> None:
        return None

    assert runner.spawn(quick()) is True
    await runner.drain(timeout=1.0)

    assert runner.active == 0, "완료된 태스크는 추적 집합에서 제거되어야 함(누수 방지)"


# ---------------------------------------------------------------- Phase 1-R2
# ADR-002 / INV-3·INV-4 — drain 은 버리지 않고 정리한다.


async def test_drain_closes_admission_before_waiting() -> None:
    """admission 을 먼저 닫지 않으면 drain 중 들어온 태스크 때문에 종료가 안 끝난다."""
    runner = BackgroundTaskRunner(max_concurrent=10)

    async def work() -> None:
        await asyncio.sleep(0.01)

    runner.spawn(work())
    await runner.drain(timeout=1.0)

    assert runner.closed is True
    assert runner.spawn(work()) is False, "종료 후에도 태스크를 받았습니다."
    assert runner.rejected_after_close == 1


async def test_drain_cancels_and_awaits_unfinished_tasks() -> None:
    """timeout 후 태스크를 **버리지 않고** 취소하고, 취소 완료까지 기다린다.

    버려진 태스크는 사라지지 않는다 — 곧 dispose 될 엔진을 건드리다 실패하고,
    그 예외는 아무도 읽지 않는다.
    """
    runner = BackgroundTaskRunner(max_concurrent=10)
    started = asyncio.Event()

    async def never_ends() -> None:
        started.set()
        await asyncio.sleep(3600)

    runner.spawn(never_ends())
    await started.wait()
    tracked = next(iter(runner._tasks))

    await runner.drain(timeout=0.05)

    assert tracked.cancelled() or tracked.done(), "미완료 태스크가 취소되지 않았습니다."
    assert runner.active == 0, "drain 후 추적 집합이 비어 있지 않습니다."


async def test_drain_empties_the_tracking_set() -> None:
    runner = BackgroundTaskRunner(max_concurrent=10)

    async def work() -> None:
        await asyncio.sleep(0.01)

    for _ in range(3):
        runner.spawn(work())

    await runner.drain(timeout=2.0)

    assert runner.active == 0


async def test_drain_consumes_task_exceptions(caplog) -> None:
    """예외를 읽지 않으면 종료 시 'never retrieved' 로만 남아 원인을 알 수 없다."""
    runner = BackgroundTaskRunner(max_concurrent=10)

    async def boom() -> None:
        raise ValueError("업무 실패")

    runner.spawn(boom())
    with caplog.at_level("WARNING", logger="background_tasks"):
        await runner.drain(timeout=1.0)

    messages = [record.getMessage() for record in caplog.records]
    assert any("error_type=ValueError" in message for message in messages)
    assert not any("업무 실패" in message for message in messages), "예외 원문이 로그에 남았습니다."


async def test_drain_on_empty_runner_still_closes_admission() -> None:
    """태스크가 없어도 종료는 종료다 — 이후 spawn 을 받으면 안 된다."""
    runner = BackgroundTaskRunner(max_concurrent=10)

    await runner.drain(timeout=1.0)

    async def work() -> None:
        return None

    assert runner.spawn(work()) is False
