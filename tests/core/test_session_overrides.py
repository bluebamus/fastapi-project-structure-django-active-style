"""테스트용 세션 override 가 운영 Dependency 의 표시를 보존한다 (service-hardening F-014).

예전 override 는 표시 없는 세션을 yield 해서, 조회 핸들러가 몰래 쓰면 운영에서는
`ReadOnlyRoutingError` 로 죽을 요청이 테스트에서는 200 으로 통과했다. 여기서는
`tests/session_overrides.py` 를 쓴 GET 라우트의 쓰기가 실제로 거부되는지, 그리고
그 헬퍼 밖에서 세션 Dependency 를 직접 바꾸는 테스트가 없는지를 고정한다.

테스트 모델은 별도 `DeclarativeBase` 를 쓴다 — 공유 metadata 를 오염시키지 않기 위해서다.
"""

import ast
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.db import session as db_session_module
from app.core.db.router import ReadOnlyRoutingError, is_read_only
from app.core.db.session import get_read_only_db_session, get_writer_db_session
from tests.session_overrides import session_overrides

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests" / "session_overrides.py"


class _TestBase(DeclarativeBase):
    """테스트 전용 metadata — 앱 Base 와 분리한다."""


class Note(_TestBase):
    __tablename__ = "override_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(String(50))


probe = FastAPI()


@probe.get("/sneaky-write")
async def sneaky_write(session: AsyncSession = Depends(get_read_only_db_session)) -> dict:
    """조회 라우트인데 쓰기를 시도한다 — 운영에서는 거부되는 회귀를 흉내 낸다."""
    session.add(Note(body="leak"))
    await session.flush()
    return {"ok": True}


@probe.post("/write")
async def write(session: AsyncSession = Depends(get_writer_db_session)) -> dict:
    session.add(Note(body="ok"))
    await session.flush()
    return {"read_only": is_read_only(session)}


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)
    probe.dependency_overrides.update(
        session_overrides(async_sessionmaker(engine, expire_on_commit=False))
    )
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://test") as c:
        yield c
    probe.dependency_overrides.clear()
    await engine.dispose()


async def test_read_only_override_rejects_a_write_from_a_get_route(client):
    with pytest.raises(ReadOnlyRoutingError):
        await client.get("/sneaky-write")


async def test_writer_override_allows_writes(client):
    response = await client.post("/write")

    assert response.status_code == 200
    assert response.json() == {"read_only": False}


# ------------------------------------------------------------------ 단일 정의 지점

_SESSION_DEPENDENCIES = {
    name
    for name, value in vars(db_session_module).items()
    if name.startswith("get_") and name.endswith("session") and callable(value)
}


def _direct_session_overrides(path: Path) -> list[int]:
    """`<x>.dependency_overrides[<세션 Dependency>] = ...` 를 쓰는 줄 번호."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    loop_names = {
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and any(
            isinstance(n, ast.Name) and n.id in _SESSION_DEPENDENCIES for n in ast.walk(node.iter)
        )
    }
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and target.value.attr == "dependency_overrides"
                and isinstance(target.slice, ast.Name)
                and target.slice.id in _SESSION_DEPENDENCIES | loop_names
            ):
                lines.append(node.lineno)
    return lines


def test_session_dependency_names_are_known():
    """검사 대상 이름이 비지 않았다 — 비면 아래 계약 테스트가 무엇이든 통과한다."""
    assert {"get_read_only_db_session", "get_writer_db_session"} <= _SESSION_DEPENDENCIES


def test_session_overrides_are_defined_only_in_the_helper():
    test_files = [
        path
        for base in (ROOT / "tests", ROOT / "app")
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts and path != HELPER
    ]
    offenders = {
        str(path.relative_to(ROOT)): lines
        for path in test_files
        if (lines := _direct_session_overrides(path))
    }

    assert not offenders, (
        "세션 Dependency 를 직접 override 하지 말고 tests/session_overrides.py 를 쓰세요 "
        f"(read-only 표시가 빠진다): {offenders}"
    )


def test_contract_check_catches_a_direct_override(tmp_path):
    """검사기 자체의 검출력 — 예전 패턴(직접 대입·루프 대입)을 잡는다."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "app.dependency_overrides[get_read_only_db_session] = _s\n"
        "for dep in (get_writer_db_session, get_read_only_db_session):\n"
        "    app.dependency_overrides[dep] = _s\n"
        "app.dependency_overrides[get_blog_service] = _svc\n",
        encoding="utf-8",
    )

    assert _direct_session_overrides(sample) == [1, 3]
