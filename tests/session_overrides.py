"""엔드포인트 테스트의 세션 Dependency override — 이 저장소의 **유일한** 정의 지점.

예전에는 테스트 파일마다 `async with maker() as session: yield session` 을 직접 써서
`get_read_only_db_session`·`get_writer_db_session` 을 모두 **표시 없는 세션**으로 바꿨다.
그러면 운영 Dependency 가 거는 `mark_read_only()`·`using_writer()` 가 테스트에서 빠져,
조회 핸들러가 몰래 쓰는 회귀가 테스트를 그대로 통과한다(service-hardening F-014).

여기서 만든 override 는 운영 Dependency 와 같은 표시를 건다. 테스트 파일은 세션을
직접 yield 하지 않고 이 모듈만 쓴다 — `tests/core/test_session_overrides.py` 가
다른 곳의 정의를 막는다.

    app.dependency_overrides.update(session_overrides(maker))
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.router import mark_read_only, using_writer
from app.core.db.session import get_read_only_db_session, get_writer_db_session

SessionHook = Callable[[AsyncSession], None]


def session_overrides(
    maker: async_sessionmaker[AsyncSession],
    *,
    on_open: SessionHook | None = None,
    writer: bool = True,
) -> dict[Callable[..., Any], Callable[..., Any]]:
    """`app.dependency_overrides.update(...)` 에 넣을 세션 override 묶음을 만든다.

    Args:
        maker: 테스트 DB(보통 in-memory SQLite)에 묶인 세션 팩토리.
        on_open: 세션을 연 직후 부르는 훅 — commit/rollback 집계처럼 세션을 감쌀 때 쓴다.
        writer: False 면 read-only 만 바꾼다. 쓰기 Dependency 를 일부러 남겨 두어
            "몰래 writer 를 잡으면 실제 DB 로 새어 실패"하게 하는 테스트용이다.
    """

    async def _read_only() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            mark_read_only(session)
            if on_open is not None:
                on_open(session)
            yield session

    async def _writer() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            using_writer(session)
            if on_open is not None:
                on_open(session)
            yield session

    overrides: dict[Callable[..., Any], Callable[..., Any]] = {get_read_only_db_session: _read_only}
    if writer:
        overrides[get_writer_db_session] = _writer
    return overrides
