"""
scripts/create_superuser.py — 슈퍼유저 만들기·승격 (Django ``createsuperuser`` 대응).

관리 경로(사용자 목록·생성, catalog 쓰기, 리포트, 접속 로그)는 슈퍼유저만 쓸 수 있고,
API 에는 "첫 슈퍼유저" 를 만드는 경로가 없다(가입은 항상 일반 사용자). 이 스크립트가
배포 직후 그 한 명을 만든다(service-hardening ADR-016). 이 계정은 ``/admin``(SQLAdmin) 로그인
계정이기도 하다 — 관리 화면은 활성 슈퍼유저만 들어간다(admin-login ADR-002). 관리 화면을 쓰지
않는 배포(``ADMIN_DISABLED=true``)에서도 관리 API 용으로 만든다.

- 사용자명이 없으면 새 슈퍼유저를 만든다 — 이메일·비밀번호가 필요하다.
- 이미 있으면 슈퍼유저로 **승격**한다. 비밀번호는 ``--set-password`` 를 줄 때만 바꾼다.
  바꾸면 API 의 비밀번호 변경과 같게 그 사용자의 refresh 토큰과 ``/admin`` 관리 세션을 커밋 전에 폐기한다.
  Redis 에 닿지 못하면 종료 코드 2 로 끝나고 비밀번호도 바꾸지 않는다(fail-closed).

비밀번호는 인자로 받지 않는다(셸 기록·프로세스 목록에 남는다). 대화형이면 ``getpass``
로 두 번 묻고, 자동화는 ``--password-stdin`` 으로 표준 입력 한 줄을 읽는다
(``docker login --password-stdin`` 과 같은 방식). 환경변수를 직접 읽지 않는 것은 설정
계약(config.py 만 환경변수를 읽는다) 때문이다 — 셸에서 ``printf '%s' "$PW" |`` 로 넘긴다.
비밀번호는 출력·로그에 남기지 않는다.

조립은 API 와 같은 부품을 쓴다 — 세션은 ``background_db_session``(요청 밖 세션),
해시기는 core provider ``get_password_hasher``(Argon2), 조회·저장은 ``UserRepository``.
커밋은 마지막에 한 번 한다.

Usage:
    uv run python -m scripts.create_superuser --username admin --email admin@example.com
    printf '%s' "$ADMIN_PASSWORD" | uv run python -m scripts.create_superuser \\
        --username admin --email admin@example.com --password-stdin
    uv run python -m scripts.create_superuser --username alice            # 기존 사용자 승격
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import TextIO

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import background_db_session
from app.core.resources import REDIS_TIMEOUT_SECONDS
from app.core.security.dependencies import (
    get_admin_session_store,
    get_password_hasher,
    get_refresh_token_store,
    get_token_service,
)
from app.core.security.password_hasher import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PasswordHasher,
)
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.services.user_service import Revocation, revoke_user_access
from app.utils.validators import EMAIL_PATTERN
from config import redis_settings

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class CommandError(Exception):
    """사용자에게 보여 줄 입력 오류(종료 코드 1)."""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.create_superuser",
        description="슈퍼유저를 만들거나 기존 사용자를 슈퍼유저로 승격한다.",
    )
    parser.add_argument("--username", required=True, help="사용자명(1~100자)")
    parser.add_argument("--email", help="이메일 — 새 사용자를 만들 때 필수")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="비밀번호를 표준 입력 한 줄에서 읽는다(자동화용). 없으면 대화형으로 묻는다.",
    )
    parser.add_argument(
        "--set-password",
        action="store_true",
        help="이미 있는 사용자의 비밀번호도 바꾼다(없으면 승격만 한다).",
    )
    return parser.parse_args(argv)


def _read_password(from_stdin: bool, stdin: TextIO) -> str:
    if from_stdin:
        password = stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("비밀번호: ")
        if getpass.getpass("비밀번호 확인: ") != password:
            raise CommandError("두 비밀번호가 다릅니다.")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise CommandError(f"비밀번호는 {PASSWORD_MIN_LENGTH}~{PASSWORD_MAX_LENGTH}자여야 합니다.")
    return password


async def create_or_promote(
    session: AsyncSession,
    hasher: PasswordHasher,
    *,
    username: str,
    email: str | None,
    password: str | None,
) -> bool:
    """슈퍼유저를 만들거나 승격한다. 새로 만들었으면 True. 커밋은 호출자가 한다.

    ``password`` 가 None 이면 기존 사용자의 비밀번호를 건드리지 않는다.
    """
    repository = UserRepository(session)
    user = await repository.get_by_username(username)
    if user is None:
        if email is None or password is None:
            raise CommandError("새 사용자를 만들려면 --email 과 비밀번호가 필요합니다.")
        await repository.create(
            {
                "username": username,
                "email": email,
                "hashed_password": hasher.hash(password),
                "is_superuser": True,
            }
        )
        return True
    changes: dict[str, object] = {"is_superuser": True}
    if password is not None:
        changes["hashed_password"] = hasher.hash(password)
    await repository.update(user.id, changes)
    return False


def _redis_from_settings() -> Redis:
    return Redis.from_url(
        redis_settings.REDIS_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )


async def _revoke_sessions(redis_factory: Callable[[], Redis], user_id: str) -> None:
    """API 의 비밀번호 변경과 같은 폐기 — 그 사용자의 refresh family 와 관리 세션(e2e-policy-2 결정 4)."""
    redis = redis_factory()
    try:
        await revoke_user_access(
            get_refresh_token_store(redis, get_token_service()),
            get_admin_session_store(redis),
            user_id,
            Revocation(admin_sessions=True, refresh=True),
        )
    finally:
        await redis.aclose()


async def _run(
    args: argparse.Namespace,
    session_factory: SessionFactory,
    hasher: PasswordHasher,
    stdin: TextIO,
    redis_factory: Callable[[], Redis],
) -> str:
    async with session_factory() as session:
        user = await UserRepository(session).get_by_username(args.username)
        password = (
            _read_password(args.password_stdin, stdin)
            if user is None or args.set_password
            else None
        )
        created = await create_or_promote(
            session, hasher, username=args.username, email=args.email, password=password
        )
        if user is not None and password is not None:
            # 커밋 **전에** 끊는다 — Redis 에 닿지 못하면 예외로 커밋을 건너뛴다(fail-closed, 비밀번호 그대로).
            # 폐기 뒤 커밋이 실패하면 세션만 끊기고 비밀번호는 그대로다(안전한 쪽).
            await _revoke_sessions(redis_factory, user.id)
        await session.commit()
    if created:
        return f"슈퍼유저 '{args.username}' 를 만들었습니다."
    suffix = "(비밀번호 변경)" if password is not None else ""
    return f"'{args.username}' 를 슈퍼유저로 승격했습니다{suffix}."


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: SessionFactory = background_db_session,
    hasher: PasswordHasher | None = None,
    stdin: TextIO | None = None,
    redis_factory: Callable[[], Redis] = _redis_from_settings,
) -> int:
    """CLI 진입점. 테스트는 세션 팩토리·해시기·표준 입력·Redis 를 바꿔 넣는다."""
    args = _parse_args(argv)
    if not 1 <= len(args.username) <= 100:
        print("사용자명은 1~100자여야 합니다.", file=sys.stderr)
        return 1
    if args.email is not None and not re.fullmatch(EMAIL_PATTERN, args.email):
        print("이메일 형식이 아닙니다.", file=sys.stderr)
        return 1
    try:
        message = asyncio.run(
            _run(
                args,
                session_factory,
                hasher or get_password_hasher(),
                stdin or sys.stdin,
                redis_factory,
            )
        )
    except CommandError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RedisError as exc:
        print(
            f"Redis 에 닿지 못해 세션을 폐기하지 못했습니다 — 비밀번호를 바꾸지 않았습니다"
            f"({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 2
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
