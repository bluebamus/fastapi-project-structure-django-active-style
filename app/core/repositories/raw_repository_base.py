"""Raw SQL Repository 기반 클래스 (계획서 §5).

`RawCRUDBase` 의 primitive 에 **관측만** 얹는다. 결과 의미는 그대로 통과시킨다 —
로깅 래퍼가 반환값을 바꾸면 primitive 의 계약이 두 곳으로 갈린다.

## 상속이 아니라 합성인 이유

이 클래스의 메서드는 primitive 에 없는 **필수** 인자(`query_name`)를 요구한다.
상속으로 두면 하위 타입이 상위 타입 자리에 들어갈 수 없어(Liskov 위반) 타입 검사가
막고, 실제로도 "RawCRUDBase 를 받는 함수" 에 이걸 넘기면 호출이 깨진다.
그래서 primitive 를 **소유**하고 앞에 관측 계층을 세운다.

ORM 쪽 `BaseRepository` 와도 당연히 무관하다 (C-7).

## 로그에 남기는 것과 남기지 않는 것

Raw 계층은 SQL 을 직접 다루므로 로그가 가장 새기 쉬운 지점이다. 남기는 항목을
화이트리스트로 고정한다.

    남긴다        질의 이름(query_name) · 소요 시간(ms) · 성공/실패 · 예외 타입
    남기지 않는다  SQL 본문 · 파라미터 값 · 결과 데이터

파라미터에는 사용자 식별자·검색어·토큰이 그대로 들어온다. "개발 환경에서만" 같은
조건부 노출도 두지 않는다 — 조건은 언젠가 뒤집히고, 그때는 이미 로그가 쌓인 뒤다 (C-5).

`query_name` 은 keyword-only 필수 인자다. 위치 인자로 두면 호출부에서 params 와
자리를 바꿔 넣거나 조용히 빠지고, 정작 장애가 났을 때 "어느 질의인지" 를 알 수 없다.

## SQL 은 Repository 가 소유한다

문장은 클래스 상수(`text(...)`)로 둔다. 요청 값으로 SQL 을 조립하지 않으며, 외부
값은 named bind 로만 들어온다. 식별자가 필요하면 `ensure_identifier()` 로 allowlist 를
통과시킨다.

    class SalesReportRawRepository(RawRepositoryBase):
        _DAILY = text("SELECT d, SUM(amount) AS total FROM orders WHERE d = :day GROUP BY d")

        async def daily(self, day):
            return await self.fetch_all(self._DAILY, {"day": day}, query_name="sales.daily")
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy import TextClause
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories.raw_crud_base import RawCRUDBase
from app.utils.logs import get_logger

__all__ = ["RawRepositoryBase"]

logger = get_logger("raw_repository")

ResultT = TypeVar("ResultT")


class RawRepositoryBase:
    """관측 가능한 Raw SQL Repository. primitive 를 소유한다(상속하지 않는다)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._primitives = RawCRUDBase(session)

    async def _observed(
        self,
        operation: str,
        query_name: str,
        run: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        """실행을 감싸 소요 시간과 성공/실패만 기록한다."""
        started = time.perf_counter()
        try:
            result = await run()
        except Exception as error:
            logger.warning(
                "[raw] %s 실패 query=%s duration=%.1fms error_type=%s",
                operation,
                query_name,
                (time.perf_counter() - started) * 1000,
                type(error).__name__,
            )
            raise
        logger.debug(
            "[raw] %s 성공 query=%s duration=%.1fms",
            operation,
            query_name,
            (time.perf_counter() - started) * 1000,
        )
        return result

    async def fetch_one(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> RowMapping | None:
        """단건 조회. 복수 행이면 실패한다 — 의미는 primitive 그대로."""
        return await self._observed(
            "fetch_one",
            query_name,
            lambda: self._primitives.fetch_one(statement, params),
        )

    async def fetch_all(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> Sequence[RowMapping]:
        """복수 조회. 0행은 빈 sequence."""
        return await self._observed(
            "fetch_all",
            query_name,
            lambda: self._primitives.fetch_all(statement, params),
        )

    async def fetch_scalar(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> Any | None:
        """단일 값 조회. 0행과 SQL NULL 은 모두 None."""
        return await self._observed(
            "fetch_scalar",
            query_name,
            lambda: self._primitives.fetch_scalar(statement, params),
        )

    async def execute(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> int | None:
        """DML 실행. commit 하지 않으며 rowcount 를 그대로 돌려준다."""
        return await self._observed(
            "execute",
            query_name,
            lambda: self._primitives.execute(statement, params),
        )
