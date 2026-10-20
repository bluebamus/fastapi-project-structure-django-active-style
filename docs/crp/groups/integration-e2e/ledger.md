# Ledger — integration-e2e (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Policy**(정책 결정 대기 — 고치지 않고 보고) / **Accept**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| W0 | HIGH | 명세 W0 | INV-2 | Fix | **Fixed** `65547fe` | Round 1 | 실물 Redis 를 쓰는 테스트가 대상 미명시 때 6379(남의 Redis)로 떨어질 수 있었다. **조치:** `tests/redis_target.py` — `REDIS_HOST`·`REDIS_PORT` 둘 다 없으면 `pytest.fail`, 명시됐는데 닿지 않으면 실패, 자식 env 에 대상을 명시(`.env` 무시). CI pytest 단계에 대상 명시. 이 저장소의 기존 테스트에는 실물 Redis 접속이 없었다(전부 가짜 주입) — 이번 하네스가 첫 사용처. 명시된 `REDIS_PORT` 가 기본 포트 검사(`test_dsn_urls`)를 뒤집던 것도 고침. |
| F-001 | HIGH | L3-8 (e2e 첫 실행) | INV-1 | Fix | **Fixed** `25b27c0` | Round 1 | replica 를 읽는 `/me` 가 500 — `RuntimeError: 'cryptography' package is required`. aiomysql 은 TLS 없이 붙고, 인증 캐시가 빈 서버(재기동 직후, 복제로 계정을 받은 replica)의 caching_sha2_password 전체 인증은 RSA 가 필요하다. pymysql 은 TLS 를 선호해 Alembic·스크립트는 됐다. 운영에서는 MySQL 재기동 뒤 모든 DB 요청이 500. **조치:** `pymysql[rsa]`. |
| F-002 | MED | L2 미인증 칸 | INV-1 | Fix | **Fixed** `893d86b`·`88b530e` | Round 1 | 토큰 없음·위조 401 에 `WWW-Authenticate` 가 없었다(RFC 9110 필수, 계획서 L2 기대값). `auto_error=False` 로 앱 고유 `UnauthorizedException` 을 쓰는데 그 예외가 헤더를 싣지 않았다. **조치:** `UnauthorizedException` 계열 기본 헤더 `Bearer`. |
| F-003 | MED | L4 상품 생성 | INV-1 | Fix | **Fixed** `848eb9d` | Round 1 | `/admin` 상품 생성·수정이 늘 실패 — 폼에 `created_at`·`updated_at` 가 있었고 타임존 없는 폼 값을 UTCDateTime 이 거부(`naive datetime 은 저장할 수 없습니다`). **조치:** `form_excluded_columns`, 모든 편집 가능 뷰 계약 테스트. |
| F-004 | MED | L5 Redis 정지 (관측 b) | INV-7 | Fix(사용자 결정) | **Fixed** `423bd26` | Round 2 | Redis 장애 때 로그인 등이 500 을 보낸 뒤 예외가 다시 올라가 traceback 두 번·연결 리셋(클라이언트 `ReadError 10054`). **조치:** ADR-006. |
| F-005 | MED | L5 replica 정지 (관측 c) | INV-8 | Fix(사용자 결정) | **Fixed** `ec04d0b` | Round 2 | replica 가 멈추면 replica 를 읽는 조회(`GET /blog/posts/{id}`, `/me` 의 사용자 조회 등)가 500. `/ready` 는 200(writer·Redis 만 본다). **조치:** ADR-007. |
| F-006 | LOW | L6 로깅 (관측 a) | INV-9 | Fix(사용자 결정) | **Fixed** `aef33c1` | Round 2 | Celery worker 의 기동 초기 줄(`[database] 라우팅 구성`)이 `celery.log` 가 아니라 `app.log` 에 남았다(logging-overhaul R-902). 웹 경로는 이미 `app.log` 에 남고 있었다. **조치:** ADR-008. |
| P-001 | LOW | L2 검증 오류 칸 | — | Policy | **Open** | Round 1 | 422 실제 본문은 `ErrorResponse{error_code:VALIDATION_ERROR, detail:[{field,message,type}]}` 인데 OpenAPI 는 38개 중 23개 operation 에서 FastAPI 기본 `HTTPValidationError`(loc·msg·type)를 광고한다(reports 1개만 `ErrorResponse`). 문서·형식 어느 쪽을 바꿔도 공개 응답 계약이 바뀐다 — 사용자 결정 대기. e2e 는 실제 형식을 고정하고 문서 값은 산출물 `openapi-422.json` 에 기록. |
| P-002 | LOW | L6 create_superuser | — | Policy | **Open** | Round 1 | `create_superuser --set-password` 로 비밀번호를 바꿔도 기존 refresh 가 살아 있다(측정: 재발급 200). API·관리 화면은 비밀번호 변경을 폐기 사유로 본다(`revocation_for`). 스크립트가 Redis 를 쓰게 할지 — 사용자 결정 대기. |
| P-003 | MED | F-004 원인 분석 | — | Policy | **Open** | Round 2 | Redis 외의 처리되지 않은 예외도 전역 `Exception` 핸들러 → 500 뒤 다시 올라가 traceback 두 번·연결 종료가 일어난다(관측: F-005 이전 replica 정지 때 조회의 `OperationalError` — `[UnhandledException]` 과 uvicorn `Exception in ASGI application` 두 레코드). 저장소 계층이 번역하는 DB 오류(예: primary 정지 때 쓰기 → `DATABASE_ERROR` 500)는 앱 예외라 해당하지 않는다. 결정 범위가 Redis 였으므로 고치지 않았다. 모든 500 에 같은 처리(다시 올리지 않기)를 할지 — 사용자 결정 대기. |
