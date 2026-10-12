"""DB 오류는 원인 코드별로 변환된다 (F-011, ADR-005).

모든 IntegrityError 를 409 "중복" 으로 응답하던 것을, 드라이버 코드(MySQL)와 메시지
(SQLite)로 갈라 중복 409 · 필수 값 422 · 참조 없음 422 · 참조 중 409 · 그 외 500 으로 바꾼다.
응답 메시지·detail 에는 SQL·바인딩 값이 실리지 않는다(C-5).
"""

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.exception import (
    ConflictException,
    DatabaseException,
    DuplicateException,
    ValidationException,
)
from app.core.repositories.db_error_translator import DBErrorTranslator
from app.core.repositories.repository_base import BaseRepository
from app.features.blog.models.models import Post
from app.features.user.models.models import User

SECRET = "victim@example.com"


class _DriverError(Exception):
    """pymysql 처럼 args[0] 에 서버 오류 코드를 싣는 DBAPI 예외."""


def _mysql_error(code: int, cls=IntegrityError):
    orig = _DriverError(code, f"error text with {SECRET}")
    return cls("INSERT INTO t (email) VALUES (%s)", (SECRET,), orig)


def _sqlite_error(message: str, cls=IntegrityError):
    return cls("INSERT INTO t (email) VALUES (?)", (SECRET,), Exception(message))


@pytest.mark.parametrize(
    ("error", "operation", "expected", "status"),
    [
        (_mysql_error(1062), "CREATE", DuplicateException, 409),
        (_mysql_error(1048), "UPDATE", ValidationException, 422),
        (_mysql_error(1364), "CREATE", ValidationException, 422),
        (_mysql_error(1364, OperationalError), "CREATE", ValidationException, 422),
        (_mysql_error(1452), "CREATE", ValidationException, 422),
        (_mysql_error(1451), "DELETE", ConflictException, 409),
        (_mysql_error(3819), "CREATE", DatabaseException, 500),  # CHECK 위반 — 미분류
        (_mysql_error(1213, OperationalError), "UPDATE", DatabaseException, 500),
        (
            _sqlite_error("UNIQUE constraint failed: users.username"),
            "CREATE",
            DuplicateException,
            409,
        ),
        (
            _sqlite_error("NOT NULL constraint failed: posts.title"),
            "UPDATE",
            ValidationException,
            422,
        ),
        (_sqlite_error("FOREIGN KEY constraint failed"), "CREATE", ValidationException, 422),
        (_sqlite_error("FOREIGN KEY constraint failed"), "DELETE", ConflictException, 409),
        (_sqlite_error("database is locked", OperationalError), "CREATE", DatabaseException, 500),
    ],
)
def test_translation_by_cause(error, operation, expected, status):
    translated = DBErrorTranslator.translate(error, model="Post", operation=operation)

    assert type(translated) is expected
    assert translated.status_code == status
    assert translated.detail == {"model": "Post"}
    assert SECRET not in translated.message
    assert "INSERT" not in translated.message


# ------------------------------------------------------------------ 실제 SQLite 경로


class PostRepo(BaseRepository[Post, str]):
    model = Post


class UserRepo(BaseRepository[User, str]):
    model = User


@pytest_asyncio.fixture
async def session():
    from app.core.db.session import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_repository_create_not_null_violation_is_422(session):
    with pytest.raises(ValidationException) as caught:
        await PostRepo(session).create({"title": None, "content": "c"})

    assert caught.value.status_code == 422


async def test_repository_update_not_null_violation_is_422(session):
    repo = PostRepo(session)
    post = await repo.create({"title": "t", "content": "c"})

    with pytest.raises(ValidationException):
        await repo.update(post.id, {"title": None})


async def test_repository_unique_violation_is_still_409(session):
    repo = UserRepo(session)
    await repo.create({"username": "hong", "email": "a@example.com"})

    with pytest.raises(DuplicateException) as caught:
        await repo.create({"username": "hong", "email": SECRET})

    assert caught.value.status_code == 409
    assert SECRET not in str(caught.value.to_response().model_dump())
