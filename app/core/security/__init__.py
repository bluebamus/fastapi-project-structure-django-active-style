"""인증·인가 코어 (service-hardening 단계 F1·F2).

기능 패키지가 서로 import 하지 않고도 같은 인증 규칙을 쓰도록 core 에 둔다.

- ``tokens.TokenService``           JWT 발급·검증(검증 규칙의 유일한 정의 지점 — C-8)
- ``refresh_store.RefreshTokenStore`` refresh 토큰 회전·재사용 탐지·family 폐기(Redis)
- ``rate_limiter.RateLimiter``       Redis 고정 창 rate limit
- ``password_hasher.PasswordHasher`` Argon2 해시·옛 bcrypt 검증(auth 가입·user 생성·운영 스크립트가 공유)
- ``authorization.Principal``        검증된 access 토큰의 주체(단계 F2)
- ``authorization.OwnershipPolicy``  소유자 또는 슈퍼유저 판정(단계 F2)
- ``dependencies``                   위 클래스들의 provider 와 ``CurrentPrincipal``·``SuperuserPrincipal``

모두 협력 객체(설정·Redis 클라이언트)를 생성자로 받는다. 기능이 함께 쓰는 provider 는
``dependencies.py`` 에, auth 전용 provider(rate limit·AuthService)는 auth 기능의
``dependencies/auth_dependencies.py`` 에 있다.
"""
