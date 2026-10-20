"""MySQL 8.4 기본 인증(caching_sha2_password)을 TLS 없이 끝까지 할 수 있어야 한다 (integration-e2e F-001).

aiomysql 은 TLS 를 기본으로 쓰지 않는다. 서버의 인증 캐시가 비어 있으면(재기동 직후, 복제로 계정을 받은
replica) 비밀번호를 RSA 로 암호화해 보내야 하고, 그 암호화는 pymysql 의 ``cryptography`` 의존성이다. 없으면
DB 를 쓰는 모든 요청이 ``RuntimeError: 'cryptography' package is required`` 로 500 이 된다.
"""

from pymysql import _auth


def test_pymysql_can_rsa_encrypt_the_password():
    assert (
        _auth._have_cryptography
    ), "cryptography 가 없습니다 — pyproject 의존성을 pymysql[rsa] 로 두세요."
