# Ledger — orm-raw-repository (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(→residual-risk) / **Wont-fix**(오탐).
> 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(코드 위치) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-5 (동일 registry 재사용) | Fix | Open | `app/core/db/session.py:227-230` 이 `import_all_models()` 로 모델을 재-discovery. `main.py:70` 의 `create_db_tables()` 호출 경로. | Phase 1. 준비된 metadata/동일 registry 결과를 재사용하도록 교체. |
| F-002 | MED | 2-1 지원 구성(PK 타입 보존) | Fix | Open | `app/core/repositories/crud_base.py:59` — `session.get(self.model, str(id))` 로 PK 를 문자열 강제 변환. | Phase 3. PK generic 도입과 함께 제거. int PK 조회가 드라이버/방언에 따라 깨질 수 있다. |
| F-003 | HIGH | INV-4 (설정 무관 read-only 보장) | Fix | Open | 가드가 `app/core/db/router.py:141-147` 의 `RoutingSession.get_bind()` 안에만 존재. `session.py:147`(라우터 on) 만 이 클래스를 쓰고 `:149`(라우터 off) 는 평범한 `async_sessionmaker` 를 쓴다. `:184` `BackgroundSessionLocal` 도 항상 비보호. | Phase 2. `DB_ROUTER_ENABLED=false` 와 백그라운드 세션에서 `mark_read_only()` 가 **무력**. |
| F-004 | MED | INV-8 (OpenAPI 스키마명) | Fix | Open | component schemas 31개 중 2개가 모듈 경로형: `app__features__auth__schemas__auth_schema__UserResponse`, `app__features__user__schemas__user_schema__UserResponse`. | Phase 9. auth/user 의 `UserResponse` 이름 충돌로 FastAPI 가 모듈 경로를 붙임. 명시적 스키마명 부여로 해소. |
| F-005 | LOW | INV-8 (tag 일관성) | Fix | Open | `tags_metadata` 선언 = `[Analytics, Blog, Health, Home, Reply, SNS, User]`. `Analytics` 선언·미사용, `Auth` 사용·미선언. | Phase 9. `Analytics` 제거 + `Auth`/`Catalog`/`Reports` 추가. |
| F-006 | HIGH | 2-2 위협 모델(무인증 Admin 방어) | Fix | Open | `app/features/admin.py:71` 에 "향후 인증 정책이 승인되면 `authentication_backend` 를 주입한다" 주석만 있고 실제 백엔드 미주입. | Phase 1 보안 설정. staging/production 에서 무인증 `/admin` 이 startup 을 통과하지 못하게 fail-fast. |
| F-007 | MED | 2-1 지원 구성(MySQL 통합) | Fix | Open | `compose.test.yaml` 부재. `.github/workflows/ci.yml` 에 MySQL service/통합 단계 없음(pytest 단계만 존재, skip/xfail 0 게이트는 이미 있음). | Phase 5. MySQL 없이 전부 skip 된 초록은 C-4 위반이므로 인프라 선행 필요. |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
- Phase 6~8 의 Raw Base / catalog / reports 는 "미구현 신규 범위"이므로 결함이 아니라
  checklist 와 development-plan §10 에서 추적한다.
-->
