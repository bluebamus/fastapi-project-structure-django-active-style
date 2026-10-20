# Run Log — integration-e2e (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지.

## 라운드 기록

### Round 0 — 2026-10-20 (base SHA: `c463ac0`) — 계획·조사
- **계획(요약):** W0(Redis 대상 명시, 별도 커밋) → W1 compose(primary+GTID replica+Redis, tmpfs) → W2 하네스(대상 안전 검사, `.env` 없는
  자식, Alembic·슈퍼유저·uvicorn·Celery) → L2 매트릭스(OpenAPI 에서 operation 을 뽑아 7칸) → L3 시나리오 → L4 Playwright → L5 장애 →
  L6 운영·로깅 → W3 인벤토리 대조(마지막에 실행) → W6 CI → 결정 3건 TDD → W7 문서 → Windows·Linux 전체 재실행.
  결함은 테스트를 먼저 커밋하고 수정을 별도 커밋으로 둔다. 정책 변경은 멈추고 ledger 에 Policy 로 남긴다.
- **인벤토리 재추출(실제 앱 import, staging 설정):**
  - API operation **38**: auth 5(register·login·refresh·logout POST, me GET), blog·sns·reply·catalog·user 각 5, home 접속 로그 5,
    reports `GET /sales/daily` 1, `/health`·`/ready` 2. 접근 수준: Public 10·PublicWrite 4·LoginRequired 12·SuperuserRequired 12.
    `DEBUG=true` 면 `/docs` 가 Public 라우트로 하나 더 붙는다(39).
  - 관리 뷰 **7** — 가능한 동작이 뷰마다 다르다: Post·SnsPost·Reply·Product 전부, UserAccessLog 삭제·상세·내보내기(생성·수정 없음),
    SalesOrder 상세·내보내기(생성·수정·삭제 없음), User 수정·삭제·상세·내보내기(생성 없음 — 비밀번호 열 때문). 모두 `created_at`
    `LocalDateFilter`. `@action` 0개.
  - Celery: `home.aggregate_access_stats`, `home.purge_expired_access_logs`(beat 매일 03:30 Asia/Seoul, 보존 365일, 5,000행 배치).
  - Redis 접두어(소스): `admin:sess:`·`admin:user_sessions:`, `admin:rl:login:`·`admin:rl:login-ip:`, `auth:rl:login:`·`auth:rl:login-ip:`·
    `auth:rl:register:`, `auth:rt:`·`auth:fam:`(`…:revoked`)·`auth:user:`(`…:fams`), Celery·kombu.
- **계획서 §1 대비 바뀐 점:** 계획서의 `admin:login` 은 Redis 키가 아니라 sqladmin 라우트 이름(`url_for('admin:login')`·`admin:logout`)이다.
  config-cleanup 으로 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS`·`API_VERSION` 이 사라졌다. logging-overhaul 로 `LOG_APP_LEVELS`·
  `LOG_RETENTION_DAYS`·프로세스별 파일(`app.log`·`error.log`/`celery.log`·`celery-error.log`)이 생기고 `LOG_BACKUP_COUNT`·`LOG_*_FILENAME`
  이 사라졌다. 관리 뷰는 "7 뷰 공통 요청 종류" 가 아니라 위처럼 뷰별 가능 동작이 다르다(N/A 사유로 반영). 이 저장소의
  `create_superuser` 에도 `--set-password` 가 있다(세션 폐기는 없다 — P-002). 기존 테스트에 실물 Redis 접속은 없었다(W0 는 예방).

### Round 1 — 2026-10-20 REQ-001
- 커밋: W0 `65547fe`, W1·W2·W5 `23199b6`, F-001 `25b27c0`, L2 `6ef2b82`, F-002 `893d86b`, L3 `e58d65e`, L4 `6680730`, F-003 `848eb9d`,
  L4 인증 `9ad5839`, L5·L6 `bc11398`, W3 `1b48222`, W6 `92210f7`·`d1845ce`.
- fail-on-revert(수정 전 코드에서 실패 확인):
  - W0: 자리표시 구현(옛 방식 — 기본 6379, 연결 확인 없음)으로 4건 실패(`DID NOT RAISE`·자식이 `.env` 의 `localhost:6379` 를 읽음).
    이 구현은 어디에도 접속하지 않는다 — 6379 에 닿은 실행 0. 연결 확인 테스트는 로컬 리스너·닫힌 포트만 쓴다.
  - F-001: 단위(`_have_cryptography`) 실패, e2e(인증 캐시를 비운 뒤 재기동) `/ready` 503 `RuntimeError`.
  - F-002: 단위 `KeyError: 'www-authenticate'`, e2e 미인증 칸 24건 실패.
  - F-003: 단위 `ProductAdmin` 실패, e2e 상품 생성 DB 0행.
- 측정: 로그인 화면 익명 세션 50회 → +50키·TTL ≤1800(R-1102), JS 꺼짐 생성 403(R-1103), `--set-password` 뒤 기존 refresh 200(P-002),
  OpenAPI 422 광고 `HTTPValidationError` 23 / `ErrorResponse` 1(P-001), 405 Allow 는 경로별 첫 라우트 메서드(R-1101).

### Round 2 — 2026-10-20 REQ-002 (관측 3건 결정)
- 관측(결정 전 현행): (a) 웹 기동 초기 줄은 `app.log` 에 있었고, Celery worker 의 초기 줄은 `celery.log` 대신 `app.log` 에 갔다.
  (b) Redis 정지 중 API 로그인 → 500 응답 뒤 연결 리셋(클라이언트 `ReadError 10054`), traceback 두 레코드(`[UnhandledException]`
  + uvicorn `Exception in ASGI application`). (c) replica 정지 중 조회 500, `/ready` 200.
- 커밋: L5·L6 기대값 고정 `bc11398`(RED), F-004 `423bd26`, F-005 `ec04d0b`, F-006 `aef33c1`, 테스트 결함 `e66d11e`·`8390ff8`,
  문서 `3041ad6`·`5999fc9`, F-002 후속(mypy) `88b530e`.
- fail-on-revert: F-004 단위 2건(예외가 핸들러 밖으로), F-005 단위 1건(재시도 없음 — 가드 2건은 원래 통과), F-006 단위 7건
  (`process_from_argv` 없음) + e2e(옛 `config.py` 를 작업 폴더 밖에 복사해 둔 뒤 되돌려 실행 → worker 초기 줄 실패, 복사본으로 복원).
- Linux 에서 찾은 테스트 결함: replica 재초기화 직후 GTID 따라잡기 전 지연을 다음 테스트가 장애로 읽음(`8390ff8`),
  README 의 `$(python` 예시를 문서 비밀값 검사가 검증기 통과 값으로 읽음(`5999fc9`, Windows 회귀는 문서 전에 돌았다).

## 수렴 판정
- `-m e2e`: Windows 237 passed(skip·xfail 0), Linux WSL 네이티브 `.env` 없는 클론 237 passed. 인벤토리 실행 칸 325·N/A 76·빈 칸 0.
- `-m "not mysql"`: Windows·Linux 통과(skip 0). `-m mysql`: 44 passed(e2e primary 의 전용 DB, skip 0).
- 열린 항목은 Policy 3건(P-001~P-003)뿐 — 사용자 결정 대기.
