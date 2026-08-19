"""Raw SQL primitive (계획서 §5).

ORM 계층과 **독립적인** 데이터 접근 경로다. `CRUDBase` 와 상속 관계를 갖지 않으며
(C-7), 세션·예외·로깅 정책만 공유한다. 만능 Base 로 합치면 두 접근의 계약이
서로를 오염시킨다 — ORM 의 identity map 과 Raw 의 결과 의미는 애초에 다른 규칙이다.

## 결과 의미를 못박는 이유

Raw 계층의 사고는 대부분 "결과를 어떻게 줄였는가" 에서 난다. `first()` 로 복수 행을
조용히 묵인하거나, scalar 가 여러 행을 버리거나, rowcount 를 bool 로 축약하면 증상은
한참 뒤에 데이터 불일치로 나타나고 원인을 SQL 에서 찾게 된다. 그래서 네 primitive 의
의미를 여기서 고정하고, 애매한 축약은 전부 예외로 만든다.

| API            | 의미                                                              |
|----------------|-------------------------------------------------------------------|
| `fetch_one`    | 0행 None · 1행 RowMapping · 복수 행이면 `MultipleResultsFound`      |
| `fetch_all`    | 0행은 빈 sequence                                                  |
| `fetch_scalar` | 0행 또는 SQL NULL 은 None · 복수 행이면 `MultipleResultsFound`      |
| `execute`      | DML 전용, commit 하지 않음, `rowcount: int | None`                  |

`fetch_scalar` 가 "0행" 과 "NULL 값" 을 구분하지 못하는 것은 의도된 계약이다.
구분이 필요하면 `fetch_one` 을 쓴다.

## 입력 계약

- 문장은 `TextClause` 만 받는다. `str` 을 받으면 호출부에서 f-string 보간이 섞여
  들어오는 것을 막을 방법이 없다.
- 외부 값은 전부 named bind parameter 로 넘긴다. `IN` 절은
  `bindparam(name, expanding=True)` 를 쓴다.
- SQL 식별자(정렬 컬럼 등)는 bind 로 넘길 수 없다. `ensure_identifier()` 로
  **코드가 소유한 allowlist** 를 통과한 값만 문자열에 넣는다.
- multi-statement 는 거부한다. 드라이버가 허용하는 경우 한 번의 호출로 의도하지 않은
  문장이 함께 실행된다.

트랜잭션 경계는 여기서 소유하지 않는다 — commit 은 쓰기 View 가 한 번 수행한다(ADR-004).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import TextClause
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RawCRUDBase", "RawSQLContractError", "ensure_identifier"]


class RawSQLContractError(RuntimeError):
    """Raw SQL 입력 계약 위반. 실행 전에 막는다."""


# 주석을 걷어낸 뒤 남은 문장 경계를 본다. 문자열 리터럴 안의 세미콜론까지 정확히
# 가리려면 parser 가 필요하지만, 이 계층의 SQL 은 Repository 소유 상수이므로
# 리터럴에 세미콜론을 넣는 상황 자체가 계약 밖이다.
_SQL_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_identifier(value: str, allowed: frozenset[str]) -> str:
    """식별자를 allowlist 로 검증하고 그대로 돌려준다.

    정렬 컬럼·테이블 이름처럼 bind parameter 로 넘길 수 없는 값을 SQL 문자열에
    넣어야 할 때 쓴다. **입력을 정제하는 것이 아니라 목록에 있는지 확인한다** —
    이스케이프로 막으려는 시도는 방언마다 빠지는 구멍이 생긴다.

    Raises:
        RawSQLContractError: allowlist 에 없거나 식별자 형태가 아닐 때.
    """
    if value not in allowed:
        raise RawSQLContractError(
            f"허용되지 않은 식별자입니다: {value!r}. "
            f"코드가 소유한 allowlist({sorted(allowed)})에 있는 값만 쓸 수 있습니다."
        )
    if not _IDENTIFIER.match(value):
        # allowlist 자체가 잘못 정의된 경우를 잡는다.
        raise RawSQLContractError(f"식별자 형태가 아닙니다: {value!r}")
    return value


def _validate(statement: Any) -> TextClause:
    """실행 전에 입력 계약을 검사한다."""
    if not isinstance(statement, TextClause):
        raise RawSQLContractError(
            "Raw SQL 은 text() 로 감싼 TextClause 만 받습니다. "
            "문자열을 그대로 넘기면 호출부의 보간을 막을 수 없습니다."
        )

    stripped = _SQL_COMMENT.sub(" ", str(statement)).strip()
    head, separator, tail = stripped.partition(";")
    if separator and tail.strip():
        raise RawSQLContractError(
            "multi-statement 는 실행하지 않습니다. 한 번에 한 문장만 넘기세요."
        )
    if not head.strip():
        raise RawSQLContractError("빈 SQL 입니다.")
    return statement


class RawCRUDBase:
    """Raw SQL 실행 primitive. ORM Base 와 상속 관계가 없다 (C-7)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch_one(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> RowMapping | None:
        """단건 조회. 복수 행이면 `MultipleResultsFound` 로 실패한다.

        `first()` 를 쓰지 않는 이유는 그것이 "여러 행이 나온 질의" 를 정상으로
        보이게 만들기 때문이다. 단건을 기대했는데 여러 행이 나왔다면 그건 질의가
        틀린 것이고, 조용히 첫 행을 쓰면 그 사실이 영영 드러나지 않는다.
        """
        result = await self.session.execute(_validate(statement), params or {})
        return result.mappings().one_or_none()

    async def fetch_all(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> Sequence[RowMapping]:
        """복수 조회. 0행은 빈 sequence 다(None 이 아니다)."""
        result = await self.session.execute(_validate(statement), params or {})
        return result.mappings().all()

    async def fetch_scalar(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> Any | None:
        """단일 값 조회. 0행과 SQL NULL 은 모두 None 이다.

        둘을 구분해야 하면 `fetch_one` 을 쓴다 — 여기서 구분하려면 sentinel 을
        도입해야 하고, sentinel 은 호출부에서 잊혀진다.
        """
        result = await self.session.execute(_validate(statement), params or {})
        return result.scalar_one_or_none()

    async def execute(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> int | None:
        """DML 실행. 영향받은 행 수를 돌려주며 commit 하지 않는다.

        Returns:
            영향받은 행 수. 드라이버가 rowcount 를 지원하지 않으면 **None**.
            `-1`(미지원 표시)을 성공 건수처럼 공개하지 않는다.
            0 은 실패가 아니라 "해당 행 없음" 이므로 bool 로 축약하지 않는다.
        """
        result = await self.session.execute(_validate(statement), params or {})
        rowcount = getattr(result, "rowcount", -1)
        return None if rowcount is None or rowcount < 0 else int(rowcount)
