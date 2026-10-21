"""MySQL 8.4 기본 인증(caching_sha2_password)을 TLS 없이 끝까지 할 수 있어야 한다 (integration-e2e F-001).

aiomysql 은 TLS 를 기본으로 쓰지 않는다. 서버의 인증 캐시가 비어 있으면(재기동 직후, 복제로 계정을 받은
replica) 비밀번호를 RSA 로 암호화해 보내야 하고, 그 암호화는 ``cryptography`` 가 한다. 없으면
DB 를 쓰는 모든 요청이 ``RuntimeError: 'cryptography' package is required`` 로 500 이 된다.

선언은 실제 드라이버의 공식 추가 옵션 하나로 둔다: ``aiomysql[rsa]``(= ``PyMySQL[rsa]`` = ``cryptography``,
e2e-policy-2 추가 결정). Alembic 이 직접 쓰는 ``pymysql`` 은 추가 옵션 없이 선언한다.
"""

import tomllib
from pathlib import Path

from pymysql import _auth

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_pymysql_can_rsa_encrypt_the_password():
    import cryptography  # noqa: F401 - 설치돼 있어야 한다

    assert (
        _auth._have_cryptography
    ), "cryptography 가 없습니다 — pyproject 의존성을 aiomysql[rsa] 로 두세요."


def test_rsa_is_declared_once_on_the_async_driver():
    deps = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    names = {
        d.split("(")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower() for d in deps
    }

    assert "aiomysql[rsa]" in names, deps
    assert "pymysql" in names and "pymysql[rsa]" not in names, deps
    assert "cryptography" not in names, deps
