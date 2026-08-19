# Residual Risk — orm-raw-repository (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | parser 없이 CTE 내부 DML 을 완전 분류할 수 없다. **Phase 2 에서 default-deny 로 구현** — `WITH` 로 시작하는 문장은 read-only 에서 전부 거부한다. 부작용: 읽기 전용 CTE 조회도 함께 막힌다(정확도 대신 안전을 택함). | MED | charter 2-2 "방어하지 않는다" 에 명시. 완전 판별은 SQL parser 의존을 요구하며 비목표. | 2026-08-18 | 읽기 전용 CTE 가 실제로 필요해지거나 SQL parser 의존성이 charter 2-1 에 추가되면 ledger 로 승격. |
| R-002 | Admin 및 catalog/reports 예제 endpoint 의 인증 범위가 제한적(예제 목적). | MED | charter 2-4 비목표 — RBAC/권한 모델은 이 그룹 범위 밖. F-006 은 "무인증 Admin 의 운영 반입 차단"까지만 다룬다. | 2026-08-18 | 예제가 운영 API 로 승격되거나 RBAC 요구가 design-baseline 에 추가되면. |
| R-003 | 실제 복제(replica) 환경에서의 라우팅·복제 지연 동작은 미검증. 테스트는 단일 MySQL 로 수행. | MED | charter 2-1 지원 구성이 단일 MySQL 통합까지만 규정. | 2026-08-18 | CI 에 replica 토폴로지가 추가되면. |
| R-004 | 성능, 커넥션 pool 튜닝, 로깅 처리량은 측정하지 않는다. | LOW | 이 그룹의 계약은 구조·정확성·보안이며 성능 SLO 는 charter 에 없음. | 2026-08-18 | 성능 SLO 가 charter 계약에 추가되면. |
| R-005 | 실제 Celery worker 를 띄운 종단 종료 시퀀스는 미검증(테스트는 FastAPI 측 종료만). | MED | development-plan §12 비목표 — FastAPI 에서 Celery 소유 자원을 종료하지 않는다. | 2026-08-18 | worker 통합 테스트가 CI 에 추가되면. |
| R-006 | 브라우저에서의 Scalar 문서 실제 렌더링은 미검증(OpenAPI 스펙 수준까지만 검사). | LOW | charter 3 인수기준이 스펙 스냅샷 검증까지만 요구. | 2026-08-18 | 브라우저 E2E 가 도입되면. |
| R-008 | 계획서 Phase 1 의 "Celery 종료" 는 이 저장소에 **대상이 없다**. FastAPI 경로(`app/features`, `app/core`, `main.py`)에 Celery 클라이언트 사용처가 없고 Celery 는 `app/celery/` 워커 측에만 있다. | LOW | development-plan §12 가 "FastAPI 에서 Celery 소유 자원 종료" 를 비목표로 명시. 대상이 없으므로 추측성 종료 코드를 넣지 않았다. | 2026-08-18 | FastAPI 요청 경로에서 `.delay()`/`send_task` 사용이 생기면 ledger 로 승격. |
| R-007 | ~~SQL 로깅이 `echo=False` 설정으로만 차단된 상태~~ → **해소(2026-08-18, Phase 1)**. `RedactingFilter` 가 DSN 자격증명과 secret 키워드를 로깅 파이프라인에서 지운다. | — | 해소됨. 남은 좁은 구멍: `exc_info` 로 실려오는 traceback 본문은 검사하지 않는다(필터 주석에 ceiling 명시). | 2026-08-18 | traceback 본문에서 secret 유출이 실제로 관측되면 ledger 로 승격. |
| R-009 | `session.info` 기반 read-only 표시는 **보안 경계가 아니다**. 같은 프로세스의 코드가 표시를 지우거나 세션을 새로 열면 우회된다. | MED | workflow-guide §7 이 명시: 운영 배포는 read-only DB credential 또는 트랜잭션 read-only 설정을 최종 방어선으로 둔다. 이 그룹의 계약은 "실수로 쓰는 것" 방지까지다. | 2026-08-18 | 신뢰 경계가 프로세스 내부로 내려오면(멀티테넌시 등) ledger 로 승격. |
| R-010 | 로컬 MySQL 통합 실행은 **WSL 배포판 생존에 의존한다**. Windows 쪽에 붙은 `wsl.exe` 프로세스가 없으면 배포판이 내려가며 컨테이너도 정지하고, 증상은 "방금 통과했는데 다음 실행에서 전부 skip" 으로 나타난다. | LOW | 이 그룹의 계약은 테스트가 **실제 실행됐는지**를 판정하는 것까지이며, skip 은 조용히 통과하지 않고 사유와 함께 드러난다(CI 는 실패 처리). 개발 환경 편의 문제라 코드로 방어하지 않는다. | 2026-08-19 | CI 가 아닌 로컬에서 이 함정 때문에 잘못된 판정이 실제로 나오면 승격. 회피법은 `compose.test.yaml` 주석에 기록했다. |
| R-011 | 지침서 §2.1 은 Service/Repository 속성과 Dependency 인자를 `db_session`/`self.db_session` 으로 규정하지만, 저장소는 `session`/`self.session` 을 쓴다(구 F-027). | LOW | 동작을 결정하는 것은 Dependency **함수 이름**(어떤 세션을 받는가)이며 그건 Phase 2 에서 정식화를 끝냈다. 남은 것은 내부 속성 표기라 계약 위반이 아니다. 92개 지점을 이름만 바꾸는 변경은 회귀 위험 대비 얻는 것이 없다(2026-08-19 사용자 결정). | 2026-08-19 | 속성명 불일치가 실제 혼선을 일으키거나, 지침서가 저장소 관례(`session`)로 현행화되면 정리한다. |
| R-012 | starlette 1.x 가 `starlette.testclient` 의 httpx 사용을 폐기 예고했다(`httpx2` 권장). 테스트 4개 파일이 `TestClient` 를 쓴다. | LOW | 라이브러리 내부 폐기 예고이며 현재 동작에는 영향이 없다. `httpx2` 전환은 테스트 하네스 교체라 이 그룹의 계약(구조·정확성·보안) 밖이다. | 2026-08-19 | starlette 가 실제로 제거하거나 CI 가 경고를 오류로 승격하면 ledger 로 승격. |
| R-013 | `uv.lock` 이 Phase 0 기준선(SHA-256 `D1BC64A8...`)에서 바뀌었다. 취약점 해소를 위한 의존성 상향(F-032)과 `pip-audit` 추가 때문이다. | LOW | MIG-001 은 lock 해시를 **기록 대상**으로 두었지 동결 대상으로 두지 않았다. 변경 사유가 취약점 해소이고 전체 suite·MySQL 통합으로 검증했다. 새 해시는 run-log Round 10 에 기록했다. | 2026-08-19 | 재현이 필요한 시점에 Round 10 의 해시를 기준으로 삼는다. |
