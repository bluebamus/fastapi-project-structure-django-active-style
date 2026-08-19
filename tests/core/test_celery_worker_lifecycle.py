"""Celery prefork 워커 자원 생명주기 (INV-10, Phase 1-R2).

fork 로 상속된 커넥션 풀을 버리지 않으면 부모와 자식이 **같은 소켓**에 쿼리를 보내
MySQL 패킷 순서가 엉킨다. 이 결함은 동시 실행이 겹쳐야 재현되므로 개발에서는 멀쩡하고
운영에서 처음 터진다 — 그래서 동작이 아니라 **구조**를 단언한다.

특히 `close=False` 는 타협이 아니라 정확성 요건이다. `close=True` 로 버리면 자식이
**부모가 쓰고 있는 소켓을 닫아버려** 고치려던 문제를 반대 방향으로 일으킨다.
"""

import asyncio

import pytest

from app.celery import task as task_module
from app.celery.worker_lifecycle import (
    on_worker_process_init,
    on_worker_process_shutdown,
    register_worker_signals,
)


class _FakeSyncEngine:
    def __init__(self, calls: list) -> None:
        self._calls = calls
        self.disposed_with: list[bool] = []

    def dispose(self, close: bool = True) -> None:
        self._calls.append("dispose")
        self.disposed_with.append(close)


class _FakeAsyncEngine:
    def __init__(self, calls: list) -> None:
        self.sync_engine = _FakeSyncEngine(calls)


@pytest.fixture
def fake_engines(monkeypatch):
    """세션 모듈의 엔진들을 가짜로 바꾼다(실제 DB 를 건드리지 않는다)."""
    from app.core.db import session as session_module

    calls: list = []
    writer = _FakeAsyncEngine(calls)
    background = _FakeAsyncEngine(calls)
    reader = _FakeAsyncEngine(calls)

    monkeypatch.setattr(session_module, "engine", writer, raising=False)
    monkeypatch.setattr(session_module, "background_engine", background, raising=False)
    monkeypatch.setattr(session_module, "read_engines", [reader], raising=False)
    return writer, background, reader


# ------------------------------------------------------------------ INV-10


def test_init_discards_every_inherited_pool(fake_engines):
    """writer·reader·background 를 **전부** 버려야 한다 — 하나라도 남으면 그게 샌다."""
    writer, background, reader = fake_engines

    on_worker_process_init()

    assert writer.sync_engine.disposed_with, "writer pool 이 폐기되지 않았습니다."
    assert reader.sync_engine.disposed_with, "reader pool 이 폐기되지 않았습니다."
    assert background.sync_engine.disposed_with, "background pool 이 폐기되지 않았습니다."


def test_init_does_not_close_parent_sockets(fake_engines):
    """`close=True` 면 자식이 부모가 쓰는 소켓을 닫는다 — 정확히 반대의 사고."""
    writer, background, reader = fake_engines

    on_worker_process_init()

    for engine in (writer, background, reader):
        assert engine.sync_engine.disposed_with == [
            False
        ], "close=False 로 버려야 부모 소켓이 살아남습니다."


def test_init_resets_the_worker_loop(fake_engines, monkeypatch):
    """부모의 루프 객체를 이어 쓰면 그 루프에 묶인 부모 커넥션을 참조하게 된다."""
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task_module, "_worker_loop", loop, raising=False)

    on_worker_process_init()

    assert task_module._worker_loop is None
    assert not loop.is_closed(), "자식이 부모와 공유하던 루프를 닫았습니다."
    loop.close()


def test_init_survives_a_failing_engine(fake_engines, monkeypatch):
    """정리 실패로 워커 기동을 막지 않는다 — 다음 커넥션 요청에서 새로 만든다."""
    writer, background, _ = fake_engines

    def boom(close: bool = True) -> None:
        raise RuntimeError("pool 폐기 실패")

    monkeypatch.setattr(writer.sync_engine, "dispose", boom)

    on_worker_process_init()  # 예외가 새어나오면 실패

    assert background.sync_engine.disposed_with == [False], "앞의 실패로 뒤가 멈췄습니다."


# ------------------------------------------------------------------ 멱등성


def test_shutdown_is_idempotent(monkeypatch):
    """Celery 는 신호를 두 번 보낼 수 있고, 정리는 두 번 불려도 안전해야 한다."""
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task_module, "_worker_loop", loop, raising=False)

    on_worker_process_shutdown()
    on_worker_process_shutdown()  # 두 번째 호출이 터지면 실패

    assert task_module._worker_loop is None
    assert loop.is_closed()


def test_shutdown_without_a_loop_is_a_noop(monkeypatch):
    monkeypatch.setattr(task_module, "_worker_loop", None, raising=False)

    on_worker_process_shutdown()

    assert task_module.close_worker_loop() is False


def test_reset_does_not_close_the_loop(monkeypatch):
    """reset 은 참조만 버린다 — 닫으면 같은 객체를 가리키는 부모에 영향이 간다."""
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task_module, "_worker_loop", loop, raising=False)

    task_module.reset_worker_loop()

    assert not loop.is_closed()
    loop.close()


# ------------------------------------------------------------------ 신호 연결


def _deref(receiver):
    """weakref 로 저장된 receiver 면 역참조한다."""
    import weakref

    if isinstance(receiver, weakref.ReferenceType):
        return receiver()
    return receiver


def test_signals_are_connected():
    """연결이 빠지면 위의 모든 로직이 **한 번도 실행되지 않는다**."""
    from celery.signals import worker_process_init, worker_process_shutdown

    register_worker_signals()  # 멱등 — app.py import 시 이미 한 번 불렸다

    # 등록된 receiver 를 **호출하지 않고** 꺼낸다. `weak=False` 로 연결했으므로
    # 저장된 값이 곧 함수다(약한 참조면 역참조한다). 여기서 호출하면 테스트가
    # 실제 핸들러를 실행해 엔진 풀을 건드린다.
    init_receivers = [_deref(receiver) for _, receiver in worker_process_init.receivers]
    shutdown_receivers = [_deref(receiver) for _, receiver in worker_process_shutdown.receivers]

    assert on_worker_process_init in init_receivers
    assert on_worker_process_shutdown in shutdown_receivers


def test_importing_celery_app_registers_signals():
    """`app.celery.app` 을 import 하는 것만으로 연결이 끝나 있어야 한다."""
    from celery.signals import worker_process_init

    import app.celery.app  # noqa: F401

    assert worker_process_init.receivers, "celery_app import 후에도 수신자가 없습니다."
