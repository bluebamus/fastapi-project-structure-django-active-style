"""인증 코어 (service-hardening 단계 F1).

기능 패키지가 서로 import 하지 않고도 같은 인증 규칙을 쓰도록 core 에 둔다.

- ``tokens.TokenService``           JWT 발급·검증(검증 규칙의 유일한 정의 지점 — C-8)
- ``refresh_store.RefreshTokenStore`` refresh 토큰 회전·재사용 탐지·family 폐기(Redis)
- ``rate_limiter.RateLimiter``       Redis 고정 창 rate limit

모두 협력 객체(설정·Redis 클라이언트)를 생성자로 받는다. 조립은 auth 기능의
``dependencies/auth_dependencies.py`` provider 가 한다.
"""
