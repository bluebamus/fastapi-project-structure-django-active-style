"""
Async-aware helper for Celery workers.

Celery workers run in a synchronous context. This module bridges a coroutine
into that sync context by reusing a single, long-lived event loop **per worker
process**.

이전 구현은 매 호출 ``asyncio.run()`` 으로 이벤트 루프를 새로 열고 닫았다.
그러나 async DB 커넥션(aiomysql)은 자신을 생성한 루프에 바인딩되고,
``background_engine`` 의 커넥션 풀은 그 커넥션을 태스크 간 캐시·재사용한다.
루프가 매번 닫히면 두 번째 태스크가 '종료된 루프에 묶인' 커넥션을 재사용하며
``RuntimeError: Event loop is closed`` 로 확정 실패한다(검수 C1/REQ-008).

Celery 기본 prefork 워커는 태스크를 프로세스 안에서 순차 실행하므로,
프로세스당 단일 영속 루프를 유지하면 재사용 커넥션이 살아있는 루프를 참조해
안전하다. (엔진/풀 설계·미들웨어 sink 경로는 변경하지 않는다.)
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

# 워커 프로세스당 하나만 생성해 재사용하는 영속 이벤트 루프.
_worker_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """동기 Celery 워커에서 async 코루틴 실행(영속 루프 재사용)."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)


def reset_worker_loop() -> None:
    """루프 참조를 비운다 — fork 직후 자식 프로세스에서 호출한다.

    모듈 전역 루프는 fork 로 **복제된다**. 자식이 부모의 루프 객체를 이어 쓰면 그
    루프에 묶인(부모의) 커넥션을 참조하게 된다. 여기서는 **닫지 않고 버린다** —
    닫으면 같은 객체를 가리키는 부모 쪽에 영향이 갈 수 있다. 자식은 다음
    `run_async()` 호출에서 자기 루프를 새로 만든다.
    """
    global _worker_loop
    _worker_loop = None


def close_worker_loop() -> bool:
    """워커 루프를 닫는다(멱등). 자식 프로세스 종료 시 호출한다.

    Returns:
        이번 호출이 실제로 루프를 닫았으면 True.
    """
    global _worker_loop
    loop = _worker_loop
    _worker_loop = None
    if loop is None or loop.is_closed():
        return False
    loop.close()
    return True
