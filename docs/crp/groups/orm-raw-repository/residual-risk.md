# Residual Risk — orm-raw-repository (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | parser 없이 CTE 내부 DML 을 완전 분류할 수 없음. read-only 가드는 default-deny 휴리스틱으로 방어한다. | MED | charter 2-2 "방어하지 않는다" 에 명시. 완전 판별은 SQL parser 의존을 요구하며 비목표. | 2026-08-18 | SQL parser 의존성이 charter 2-1 지원 구성에 추가되면 ledger 로 승격. |
| R-002 | Admin 및 catalog/reports 예제 endpoint 의 인증 범위가 제한적(예제 목적). | MED | charter 2-4 비목표 — RBAC/권한 모델은 이 그룹 범위 밖. F-006 은 "무인증 Admin 의 운영 반입 차단"까지만 다룬다. | 2026-08-18 | 예제가 운영 API 로 승격되거나 RBAC 요구가 design-baseline 에 추가되면. |
| R-003 | 실제 복제(replica) 환경에서의 라우팅·복제 지연 동작은 미검증. 테스트는 단일 MySQL 로 수행. | MED | charter 2-1 지원 구성이 단일 MySQL 통합까지만 규정. | 2026-08-18 | CI 에 replica 토폴로지가 추가되면. |
| R-004 | 성능, 커넥션 pool 튜닝, 로깅 처리량은 측정하지 않는다. | LOW | 이 그룹의 계약은 구조·정확성·보안이며 성능 SLO 는 charter 에 없음. | 2026-08-18 | 성능 SLO 가 charter 계약에 추가되면. |
| R-005 | 실제 Celery worker 를 띄운 종단 종료 시퀀스는 미검증(테스트는 FastAPI 측 종료만). | MED | development-plan §12 비목표 — FastAPI 에서 Celery 소유 자원을 종료하지 않는다. | 2026-08-18 | worker 통합 테스트가 CI 에 추가되면. |
| R-006 | 브라우저에서의 Scalar 문서 실제 렌더링은 미검증(OpenAPI 스펙 수준까지만 검사). | LOW | charter 3 인수기준이 스펙 스냅샷 검증까지만 요구. | 2026-08-18 | 브라우저 E2E 가 도입되면. |
| R-008 | 계획서 Phase 1 의 "Celery 종료" 는 이 저장소에 **대상이 없다**. FastAPI 경로(`app/features`, `app/core`, `main.py`)에 Celery 클라이언트 사용처가 없고 Celery 는 `app/celery/` 워커 측에만 있다. | LOW | development-plan §12 가 "FastAPI 에서 Celery 소유 자원 종료" 를 비목표로 명시. 대상이 없으므로 추측성 종료 코드를 넣지 않았다. | 2026-08-18 | FastAPI 요청 경로에서 `.delay()`/`send_task` 사용이 생기면 ledger 로 승격. |
| R-007 | ~~SQL 로깅이 `echo=False` 설정으로만 차단된 상태~~ → **해소(2026-08-18, Phase 1)**. `RedactingFilter` 가 DSN 자격증명과 secret 키워드를 로깅 파이프라인에서 지운다. | — | 해소됨. 남은 좁은 구멍: `exc_info` 로 실려오는 traceback 본문은 검사하지 않는다(필터 주석에 ceiling 명시). | 2026-08-18 | traceback 본문에서 secret 유출이 실제로 관측되면 ledger 로 승격. |
