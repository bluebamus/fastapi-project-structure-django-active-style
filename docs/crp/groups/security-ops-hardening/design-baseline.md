# Design Baseline — security-ops-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력:
- 2026-10-19: 최초 선택 = 보통. 사유 — 사용자가 항목(보안 결함·보존 1년·`.env` 설정·15분 유지·로그인 CSRF·
  날짜 필터)을 정했고, 감독자가 명세로 세부를 확정했다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

리뷰 이후 남은 운영 보안 항목을 닫는다. ① DB 예외 문자열·SQLAlchemy 로그에 바인드 값(이메일·해시·토큰)이
실린다 — 엔진에 `hide_parameters` 가 없었다(리뷰 R-05 "부분 해결", log-redaction-fixes R-402, service-hardening
R-204). ② 접속 로그에 보존 기간·파기 절차가 없다(log-redaction-fixes R-401). ③ 관리 로그인 폼에 CSRF 토큰이
없다(admin-login R-302). ④ 관리 목록에서 `created_at` 으로 거를 수 없다(admin-login R-310).

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "보안결함 진행해줘. 접속 로그 보존 기간은 기본 1년으로 설정하고 이는 설정값으로 설정이 가능하도록 만들어줘. .env에 설정이 되도록 해줘. 15분 유지한다. ... 관리 화면 로그인폼에 csrf 토큰 작업을 진행해줘. 관리 화면 목록에 created_at 날자 필터 작업해줘." (원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합·데이터 전달·자동 작업은 주입, 모든 단계 단위 테스트·fail-on-revert) | ① 모든 엔진 `hide_parameters=True`(정본 옵션 하나) ② `ACCESS_LOG_RETENTION_DAYS`(기본 365, `.env`, 0=삭제 안 함, 음수 거부) + 배치 삭제 서비스 + Celery beat 매일 03:30 ③ `/admin/login` synchronizer token CSRF ④ 관리 목록 `created_at` 지역 날짜 필터 ⑤ 액세스 토큰 15분·권한 회수 지연 **유지**(결정 기록) ⑥ 문서·review | Active | ADR-001~ADR-005 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | **엔진 안전 옵션의 정본은 `app/core/db/session.py` 의 `ENGINE_SAFETY_OPTIONS = {"hide_parameters": True}` 하나다.** writer·reader(`_create_read_engine`)·background 엔진과 Alembic `engine_from_config` 가 `**ENGINE_SAFETY_OPTIONS` 로 펼친다. 새 생성 지점이 빠뜨리면 AST 검사(`test_every_engine_construction_site_spreads_the_safety_options`)가 실패한다. | 바인드 값은 키워드 꼴이 아니라 `RedactingFilter` 로 지울 수 없다 — 근원(엔진)에서 막아야 한다. 지점마다 `hide_parameters=True` 를 적으면 다음 엔진이 빠뜨린다. SQL 문은 남아 진단은 된다. Celery 는 같은 엔진 객체를 쓰므로 별도 지점이 없다. | Active | — |
| ADR-002 | 2026-10-19 | **보존 정리는 home 의 `AccessLogRetentionService` 한 클래스가 정책을, `UserAccessLogRepository.delete_created_before(cutoff, limit)` 가 쿼리를 맡는다.** 기준 `created_at < now(UTC) − N일`(경계 행은 남김), 5,000행 배치, **배치마다 커밋**, 지운 총 수 반환, 시계 주입. 쿼리는 "id 를 LIMIT 으로 고른 뒤 그 id 로 DELETE" 두 단계. 태스크 `home.purge_expired_access_logs` 가 provider `build_access_log_retention_service(session)` 로 조립하고, 같은 `tasks.py` 가 `celery_app.conf.beat_schedule` 에 `crontab(hour=3, minute=30)`(Celery timezone = `TIME_ZONE`)을 등록한다. 설정 `ACCESS_LOG_RETENTION_DAYS: int = Field(365, ge=0)`(MiddlewareSettings 의 접속 로그 묶음), `0` 이면 쿼리 없이 0 반환. | 다른 서비스와 달리 트랜잭션 경계를 스스로 정한다 — 1년 치를 한 트랜잭션으로 지우면 잠금·undo 가 커져 적재 INSERT 까지 막는다. MySQL 은 `DELETE ... WHERE id IN (SELECT ... LIMIT n)` 을 거부하고 SQLite 기본 빌드는 `DELETE ... LIMIT` 이 없다 — 두 단계는 양쪽에서 같다. beat 등록을 기능에 두면 중앙 Celery 앱이 기능을 import 하지 않는다(include 와 같은 철학). beat 도 시작 시 include 를 import 한다(celery `Beat.init_loader` → `loader.init_worker`). | Active | — |
| ADR-003 | 2026-10-19 | **관리 로그인 CSRF 는 synchronizer token 이다.** `AdminAuthBackend.csrf_token(request)` 가 세션 `csrf_token` 을 돌려주고 없으면 `secrets.token_urlsafe(32)` 로 만든다. `create_admin_interface` 가 이 메서드를 sqladmin 템플릿 전역 `csrf_token` 으로 등록하고 `login.html` 이 hidden 필드에 싣는다. `login()` 은 **레이트 리밋보다 먼저** 폼 값과 세션 값을 `hmac.compare_digest`(bytes)로 비교해 없거나 다르면 403(`CSRF_FAILED_MESSAGE`)으로 다시 그린다. 로그인 성공의 `session.clear()` 가 회전을 맡는다. | sqladmin 0.32 의 GET `/admin/login` 은 컨텍스트 없이 `TemplateResponse(request, "sqladmin/login.html")` 를 부른다 — 템플릿 전역 함수가 GET·403·400·429 재표시 모두를 한 경로로 덮는 가장 단순한 방법이다. 레이트 리밋 전에 보면 위조 요청이 관리자의 시도 횟수를 깎지 못한다. str 끼리의 `compare_digest` 는 비 ASCII 입력에서 TypeError(500)라 bytes 로 비교한다. | Active | — |
| ADR-004 | 2026-10-19 | **관리 목록 날짜 필터는 core 의 `LocalDateFilter(OperationColumnFilter)` 한 클래스다**(`app/core/admin_filters.py`). 입력 `YYYY-MM-DD`(정규식 + `date.fromisoformat`), 연산 `on`(같은 날)·`on_or_after`(이후, 포함)·`before`(이전, 미포함). 지역 날짜의 [자정, 다음 자정)을 `datetime.combine(..., tzinfo=TIME_ZONE).astimezone(UTC)` 로 만들어 범위 질의. 잘못된 날짜·연산은 필터 없이 목록(200) + WARNING. `created_at` 이 있는 7개 뷰(home·blog·reply·sns·user·catalog·reports)에 붙인다. 빠른 선택(오늘·7일·30일)은 두지 않는다. | sqladmin 의 연산 필터는 `UTCDateTime`(TypeDecorator)을 날짜형으로 보지 못해 문자열을 바인딩 → 500 이었다. 연산 필터 프로토콜(`has_operator`·`get_operation_options_for_model`·`get_filtered_query(query, operation, value, model)`)을 그대로 따르므로 sqladmin UI 가 바뀌지 않는다. `combine` + zoneinfo 는 서머타임 날(23·25시간)도 맞다. sqladmin 의 연산 필터 화면은 값 입력이 필수(`required`)라 한 필터에 빠른 선택을 담을 수 없다 — "최근 7일" 은 `이후(포함)` 에 날짜를 넣는다. | Active | — |
| ADR-005 | 2026-10-19 | **액세스 토큰 수명 15분(`ACCESS_TOKEN_EXPIRE_MINUTES`)과 "권한 회수(강등·비활성화)는 access 토큰 만료까지 지연" 을 유지한다** — 사용자 결정. service-hardening R-201·R-211 에 "사용자 결정으로 수용(2026-10-19)" 을 덧붙인다. 관리 세션의 Redis 이전(서버측 폐기)은 이번 범위 밖(사용자 결정 대기, R-602). | 사용자 원문 "15분 유지한다". 즉시 폐기는 요청마다 저장소 조회가 필요해 무상태 판정(service-hardening ADR-014)을 버려야 한다. | Active | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 모든 SQLAlchemy 엔진은 `ENGINE_SAFETY_OPTIONS` 를 펼친다(테스트 엔진 제외) — ADR-001.
- C-2: 보존 삭제는 배치·배치별 커밋이고 경계(`<`)를 지킨다. `0` 은 아무것도 지우지 않는다 — ADR-002.
- C-3: 중앙 Celery 앱은 기능을 import 하지 않는다. beat 항목은 기능의 `tasks.py` 가 등록한다 — ADR-002.
- C-4: CSRF 확인은 레이트 리밋·자격 확인보다 먼저이고 상수 시간 비교다 — ADR-003.
- C-5: 날짜 필터는 잘못된 입력에 500 을 내지 않는다 — ADR-004.
- C-6: 스키마 변경 없음(alembic head `a7c3e9f1b2d4` 단일). 테스트는 실제 DB·Redis 에 접속하지 않는다(SQLite·fakeredis·mock).
- C-7: 접속 로그 원문 저장(session_id·Referer·XFF)은 바꾸지 않는다(log-redaction-fixes ADR-003, 사용자 결정).

## 5. 변경 이력
- v0.1 (2026-10-19): 최초 작성. REQ-001, ADR-001~ADR-005, C-1~C-7. 이전 그룹 R-201·R-204·R-211(service-hardening),
  R-302·R-310(admin-login), R-401·R-402(log-redaction-fixes) 에 상태 주석 append.
