"""PK 타입 보존과 `pk_attr` 계약 (ledger F-002, 계획서 §4).

`CRUDBase._get()` 이 `session.get(self.model, str(id))` 로 PK 를 문자열로 강제
변환하고 있었다. 이 프로젝트의 모델이 마침 문자열 UUID PK 라서 드러나지 않았을 뿐,
정수 PK 나 `UUID` 객체 PK 를 쓰는 모델에서는 조회가 조용히 빗나간다.

PK 는 `BaseRepository[ModelT, PrimaryKeyT]` 가 선언한 타입 그대로 전달되어야 한다.
"""

import uuid

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.repositories.crud_base import CRUDBase


class _SpySession:
    """`session.get()` 에 무엇이 넘어왔는지만 기록하는 대역."""

    def __init__(self):
        self.received = []

    async def get(self, model, pk):
        self.received.append(pk)
        return None


class _TestBase(DeclarativeBase):
    """테스트 전용 metadata — 공유 Base 와 분리한다(workflow-guide §14).

    앱 Base 에 붙이면 이 더미 테이블이 Base.metadata 로 새어 들어가 Alembic
    마이그레이션 대조 테스트를 깨뜨린다(실제로 한 번 그렇게 깨졌다).
    """


class _Dummy(_TestBase):
    __tablename__ = "pk_generic_dummy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[int] = mapped_column(Integer, nullable=True)


@pytest.fixture
def spy():
    return _SpySession()


@pytest.fixture
def repository(spy):
    class _Repo(CRUDBase[_Dummy, str]):
        model = _Dummy

    return _Repo(spy)


@pytest.mark.parametrize(
    "primary_key",
    [
        "8f14e45f-ea3b-4f2a-9f1b-1c2d3e4f5a6b",
        42,
        uuid.UUID("8f14e45f-ea3b-4f2a-9f1b-1c2d3e4f5a6b"),
        ("composite", 1),
    ],
    ids=["str", "int", "uuid", "tuple"],
)
async def test_primary_key_is_passed_through_unchanged(repository, spy, primary_key):
    await repository._get(primary_key)

    assert spy.received == [primary_key]
    assert type(spy.received[0]) is type(
        primary_key
    ), "PK 타입이 변환됐습니다 — 정수/UUID PK 조회가 빗나갑니다."


async def test_integer_primary_key_is_not_stringified(repository, spy):
    """회귀 고정 — 예전 구현은 여기서 '42' 를 넘겼다."""
    await repository._get(42)

    assert spy.received == [42]
    assert spy.received[0] != "42"


def test_default_pk_attr_is_id(repository):
    assert repository.pk_attr == "id"


def test_pk_column_follows_pk_attr(spy):
    """PK 컬럼 이름이 `id` 가 아닌 모델도 지원한다."""

    class _Repo(CRUDBase[_Dummy, int]):
        model = _Dummy
        pk_attr = "code"

    assert _Repo(spy)._pk is _Dummy.code


def test_base_repository_accepts_two_type_parameters():
    from app.core.repositories.repository_base import BaseRepository

    class _Typed(BaseRepository[_Dummy, str]):
        model = _Dummy

    assert _Typed.model is _Dummy


def test_base_repository_still_accepts_single_parameter():
    """기존 선언 `BaseRepository[Model]` 도 깨지지 않는다(PK 타입 기본값)."""
    from app.core.repositories.repository_base import BaseRepository

    class _Legacy(BaseRepository[_Dummy]):
        model = _Dummy

    assert _Legacy.model is _Dummy
