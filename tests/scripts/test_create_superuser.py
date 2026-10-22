"""scripts/create_superuser.py — 슈퍼유저 생성·승격 (service-hardening F2, ADR-016).

실제 ``main()`` 을 SQLite 파일 DB 에 대고 부른다. 세션 팩토리만 바꿔 넣고, 해시기는 core
provider 의 진짜 ``PasswordHasher``(Argon2)를 쓴다.
"""

import asyncio
import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.session import Base
from app.core.security.password_hasher import PasswordHasher
from app.features.user.models.models import User
from scripts import create_superuser


@pytest.fixture
def db(tmp_path):
    """``(session_factory, load_user)`` — main() 이 쓰는 세션과 결과 확인용 조회."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'su.db').as_posix()}"

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        # main() 은 asyncio.run 으로 새 루프를 연다 — 엔진도 그 루프 안에서 만들고 닫는다.
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    async def _create_tables() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    def load_user(username: str) -> User | None:
        async def _load() -> User | None:
            async with session_factory() as session:
                return await session.scalar(select(User).where(User.username == username))

        return asyncio.run(_load())

    asyncio.run(_create_tables())
    return session_factory, load_user


def _run(session_factory, *args: str, stdin: str = "", redis_factory=None) -> int:
    server = FakeServer()
    return create_superuser.main(
        list(args),
        session_factory=session_factory,
        stdin=io.StringIO(stdin),
        redis_factory=redis_factory or (lambda: FakeAsyncRedis(server=server)),
    )


def test_creates_superuser_with_argon2_hash(db, capsys):
    session_factory, load_user = db

    code = _run(
        session_factory,
        "--username",
        "admin",
        "--email",
        "admin@example.com",
        "--password-stdin",
        stdin="s3cret-pass\n",
    )

    assert code == 0
    user = load_user("admin")
    assert user is not None and user.is_superuser and user.is_active
    assert user.hashed_password is not None and user.hashed_password.startswith("$argon2")
    ok, _ = PasswordHasher().verify_and_update("s3cret-pass", user.hashed_password)
    assert ok
    out = capsys.readouterr()
    assert "s3cret-pass" not in out.out + out.err


def test_promotes_existing_user_without_touching_password(db):
    session_factory, load_user = db
    _run(
        session_factory,
        "--username",
        "alice",
        "--email",
        "alice@example.com",
        "--password-stdin",
        stdin="original-pass\n",
    )

    async def _demote() -> None:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.username == "alice"))
            assert user is not None
            user.is_superuser = False
            await session.commit()

    asyncio.run(_demote())
    before = load_user("alice")
    assert before is not None and not before.is_superuser

    # 비밀번호를 묻지 않는다 — 표준 입력이 비어 있어도 성공한다.
    assert _run(session_factory, "--username", "alice") == 0

    after = load_user("alice")
    assert after is not None and after.is_superuser
    assert after.hashed_password == before.hashed_password


def test_set_password_changes_existing_password(db):
    session_factory, load_user = db
    _run(
        session_factory,
        "--username",
        "alice",
        "--email",
        "alice@example.com",
        "--password-stdin",
        stdin="original-pass\n",
    )

    code = _run(
        session_factory,
        "--username",
        "alice",
        "--set-password",
        "--password-stdin",
        stdin="rotated-pass\n",
    )

    assert code == 0
    user = load_user("alice")
    assert user is not None and user.hashed_password is not None
    assert PasswordHasher().verify_and_update("rotated-pass", user.hashed_password)[0]


def test_interactive_prompt_requires_matching_confirmation(db, monkeypatch):
    session_factory, load_user = db
    answers = iter(["s3cret-pass", "different-pass"])
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": next(answers))

    code = _run(session_factory, "--username", "admin", "--email", "admin@example.com")

    assert code == 1
    assert load_user("admin") is None


def test_interactive_prompt_creates_user(db, monkeypatch):
    session_factory, load_user = db
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": "s3cret-pass")

    assert _run(session_factory, "--username", "admin", "--email", "admin@example.com") == 0
    user = load_user("admin")
    assert user is not None and user.is_superuser


@pytest.mark.parametrize(
    ("args", "stdin"),
    [
        (["--username", "admin", "--password-stdin"], "s3cret-pass\n"),  # 새 사용자인데 이메일 없음
        (["--username", "admin", "--email", "admin@example.com", "--password-stdin"], "short\n"),
        (["--username", "admin", "--email", "not-an-email", "--password-stdin"], "s3cret-pass\n"),
    ],
    ids=["missing-email", "short-password", "invalid-email"],
)
def test_rejects_invalid_input_without_writing(db, args, stdin):
    session_factory, load_user = db

    assert _run(session_factory, *args, stdin=stdin) == 1
    assert load_user("admin") is None


def test_script_reuses_core_providers():
    """조립은 API 와 같은 부품이다 — 요청 밖 세션과 core 해시기 provider (ADR-016)."""
    from app.core.db.session import background_db_session
    from app.core.security.dependencies import get_password_hasher

    assert create_superuser.background_db_session is background_db_session
    assert create_superuser.get_password_hasher is get_password_hasher
    assert create_superuser.main.__kwdefaults__["session_factory"] is background_db_session


def _alice(session_factory) -> None:
    assert (
        _run(
            session_factory,
            "--username",
            "alice",
            "--email",
            "alice@example.com",
            "--password-stdin",
            stdin="original-pass\n",
        )
        == 0
    )


def test_set_password_revokes_refresh_and_admin_sessions(db):
    """CLI 비밀번호 변경도 API 와 같게 그 사용자의 refresh family 와 관리 세션을 끊는다
    (integration-e2e ADR-010, P-002)."""
    from app.core.security.admin_session import AdminSessionStore
    from app.core.security.refresh_store import RefreshTokenStore

    session_factory, load_user = db
    _alice(session_factory)
    user = load_user("alice")
    assert user is not None
    server = FakeServer()

    async def _sign_in() -> None:
        redis = FakeAsyncRedis(server=server)
        await RefreshTokenStore(redis, 3600).register("jti-1", user.id, "fam-1")
        sessions = AdminSessionStore(redis, "k" * 32, max_age=3600, idle=600)
        await sessions.save("sid-1", {"user_id": user.id}, sessions.now(), create=True)

    asyncio.run(_sign_in())

    code = _run(
        session_factory,
        "--username",
        "alice",
        "--set-password",
        "--password-stdin",
        stdin="rotated-pass\n",
        redis_factory=lambda: FakeAsyncRedis(server=server),
    )

    async def _state() -> tuple[bool, int]:
        redis = FakeAsyncRedis(server=server)
        revoked = await RefreshTokenStore(redis, 3600).is_family_revoked("fam-1")
        return revoked, await redis.exists(AdminSessionStore.user_key(user.id))

    assert code == 0
    assert asyncio.run(_state()) == (True, 0)


class _DownRedis(FakeAsyncRedis):
    async def smembers(self, *args, **kwargs):
        raise RedisConnectionError("down")


def test_set_password_fails_closed_without_redis(db, capsys):
    """Redis 에 닿지 못하면 0 이 아닌 코드로 끝나고 비밀번호도 바뀌지 않는다(fail-closed)."""
    session_factory, load_user = db
    _alice(session_factory)
    before = load_user("alice")
    assert before is not None

    code = _run(
        session_factory,
        "--username",
        "alice",
        "--set-password",
        "--password-stdin",
        stdin="rotated-pass\n",
        redis_factory=_DownRedis,
    )

    assert code != 0
    after = load_user("alice")
    assert after is not None and after.hashed_password == before.hashed_password
    err = capsys.readouterr().err
    assert "Redis" in err and "rotated-pass" not in err
