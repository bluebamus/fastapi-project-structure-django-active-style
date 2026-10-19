# Residual Risk — log-redaction-fixes (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-401 | **보존 기간 도입(2026-10-19, security-ops-hardening F-002)** — `ACCESS_LOG_RETENTION_DAYS`(기본 365일)가 지난 행을 Celery beat 가 매일 03:30 배치로 지운다. 원문 저장 자체는 사용자 결정 그대로다. 원 기록: 접속 로그 테이블이 `session_id` 쿠키·Referer·X-Forwarded-For 를 원문 그대로 저장한다 — **사용자 결정으로 수용**. | MED | ADR-003. 사용자가 유지를 결정했다. 조회 API 는 슈퍼유저 전용이고 `query_string` 의 민감 키 값은 이미 가린다. 보존 기간·파기 절차는 없다(ARCHITECTURE §10.4). | 2026-10-13 | 사용자가 개인정보 처리 방침을 바꾸거나 보존 기간 요구가 생기면 charter 를 개정한다. |
| R-402 | **SQL 바인드 값은 해소(2026-10-19, security-ops-hardening F-001)** — 모든 엔진의 `hide_parameters=True`(`ENGINE_SAFETY_OPTIONS`)로 DB 예외·SQLAlchemy 로그에 바인드 값이 실리지 않는다. 그 밖의 맨 값·다른 인증 스킴은 그대로다. 원 기록: 마스킹은 꼴(DSN 자격증명·`키=값`/`키: 값`·`Bearer <토큰>`)로만 판정한다 — 맨 값으로 실린 비밀값, `Basic` 등 다른 인증 스킴, 키워드 목록 밖의 이름은 가리지 않는다. 반대로 `bearer` 뒤 단어는 산문이어도 `***` 가 된다. | LOW | ADR-002. 값 자체를 알아볼 수 없으므로 꼴 규칙이 한계다. `Basic` 은 산문의 "basic" 오탐이 커서 넣지 않았다. | 2026-10-13 | 다른 꼴의 유출이 관측되면 `redact()` 에 규칙을 더한다(정본 하나 유지). |
| R-403 | 필터가 traceback 을 `logging.Formatter().formatException` 으로 미리 렌더한다 — `formatException` 을 바꾼 포매터(예: 구조화 JSON)를 나중에 붙이면 그 포매터의 traceback 형식이 아니라 기본 형식 문자열을 받는다. | LOW | ADR-002. 지금 저장소의 포매터(`TzFormatter`·uvicorn·Celery)는 모두 기본 형식이다. | 2026-10-13 | 구조화 로그 포매터를 도입하면 그 포매터가 `exc_text` 대신 `exc_info` 를 쓰는지 확인하고 필터를 맞춘다. |
| R-404 | 실제 `uvicorn main:app` 프로세스·실제 Celery 워커로는 확인하지 않았다 — uvicorn 은 같은 프로세스에서 `uvicorn.config.LOGGING_CONFIG` 적용 → `configure_logging()` 순서를 재현했고, Celery 는 수신자 연결과 수신자 호출을 확인했다. | LOW | 로컬 정책(docker·MySQL 미사용). 수신자 로직은 단위로 고정했다. | 2026-10-13 | 운영 로그에서 가려지지 않은 traceback 이 관측되면 실제 프로세스 스모크를 CI 에 더한다. |
| R-405 | Redis 버전 확인은 `INFO` 가 막히면 건너뛴다(WARNING). fakeredis 는 INFO 를 지원하지 않아 테스트·로컬 스모크는 항상 이 경로다 — 실제 `INFO server` 응답 파싱은 가짜 응답으로만 시험했다. | LOW | ADR-005. 관리형 Redis 의 INFO 차단은 버전 문제가 아니다. compose 의 Redis 7.4(`mysql` job 은 Redis 를 띄우지 않는다)로는 아직 돌지 않았다. | 2026-10-13 | CI 에 실물 Redis 단계가 생기면 버전 확인 통과 로그를 단언하는 테스트를 더한다. |
| R-406 | **해소(2026-10-13, access-policy F-001)** — 뷰 단위 접근 수준 선언과 기동 시 기본 거부(`AccessPolicyGuard`, 숨긴 경로 포함)로 닫혔다. 원 기록: **새 라우터에 인증을 빠뜨려도 막는 기본값이 없다** — 보호는 경로별 `Depends`(`CurrentPrincipal`·`SuperuserPrincipal`·`require_superuser`)와 라우터 `dependencies=` 로만 걸리고, 전역 미들웨어·registry 기본 의존성·생성기 템플릿의 인증은 없다. 막아 주는 것은 `tests/test_authorization.py::test_every_operation_is_classified`(OpenAPI 의 모든 `/api*`·`/health`·`/ready` operation 이 `POLICY` 표에 있고 security 표시가 분류와 맞아야 함)뿐이다 — 새 operation 을 PUBLIC 으로 분류하면 통과하고, `include_in_schema=False` 라우트는 이 검사 밖이다. | MED | ADR-006 — 명세 §5 는 조사·보고만. 판단은 사용자 몫(감독자 보고에 전체 라우트 표 포함). | 2026-10-13 | 사용자가 기본 거부(예: registry 가 라우터에 기본 의존성을 거는 방식)나 스키마 밖 라우트 검사를 요구하면 charter 를 개정한다. |
| R-407 | 커버리지 하한이 0 이라 커버리지가 떨어져도 CI 가 막지 않는다 — **사용자 결정으로 수용**. | LOW | ADR-007(REQ-002). 수치는 CI 로그에 남는다(현재 96%). | 2026-10-13 | 사용자가 하한을 정하면 `fail_under` 하나만 올린다(DEVELOPMENT §11). |

<!--
규칙:
- 여기 있는 항목을 다음 라운드에서 새 finding 으로 다시 올리지 않는다.
- 재평가 조건이 참이 되면 ledger 로 승격한다(그때 비로소 "결함").
-->
