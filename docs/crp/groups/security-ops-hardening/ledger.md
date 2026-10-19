# Ledger — security-ops-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001, 감독자 확인, 리뷰 R-05, log-redaction-fixes R-402, service-hardening R-204 | INV-1 | Fix | **Fixed** | Round 1 | `app/core/db/session.py` 의 엔진 생성 지점 3곳과 Alembic 에 `hide_parameters` 가 없어 `IntegrityError` 등의 `str()`·`logger.exception`·echo 로그에 바인드 값(이메일·해시)이 그대로 실렸다(재현: SQLite 고유 제약 위반 문자열에 값이 보임). **조치:** 정본 `ENGINE_SAFETY_OPTIONS` 를 4개 지점이 펼침(ADR-001). 회귀: `tests/core/test_hide_parameters.py`. |
| F-002 | MED | REQ-001, log-redaction-fixes R-401 | INV-2·INV-3 | Fix | **Fixed** | Round 1 | 접속 로그 보존 기간·파기 절차가 없다. **조치:** `ACCESS_LOG_RETENTION_DAYS`(기본 365), `AccessLogRetentionService` 배치 삭제, beat 매일 03:30(ADR-002). 회귀: `app/features/home/tests/test_access_log_retention.py`, MySQL 1건. |
| F-003 | MED | REQ-001, admin-login R-302 | INV-4 | Fix | **Fixed** | Round 1 | `/admin/login` POST 에 CSRF 토큰이 없어 다른 사이트가 관리자 브라우저로 로그인 POST 를 보내 레이트 리밋 카운터를 소진시키거나(관리자 잠금) 로그인 CSRF 를 시도할 수 있다(SameSite 미지원·같은 사이트 다른 오리진). **조치:** synchronizer token, 레이트 리밋 전 상수 시간 비교(ADR-003). |
| F-004 | LOW | REQ-001, admin-login R-310 | INV-5 | Fix | **Fixed** | Round 1 | 관리 목록에서 `created_at` 으로 거를 수 없다(기본 연산 필터는 500). **조치:** core `LocalDateFilter` 를 7개 뷰에(ADR-004). |
| F-005 | — | REQ-001 "15분 유지한다" | — | Accept-out-of-scope | **Accepted** | Round 1 | 액세스 토큰 15분·권한 회수의 만료까지 지연은 사용자 결정으로 유지(ADR-005). service-hardening R-201·R-211 에 상태 주석. |
| F-006 | — | Round 1 조사 | — | Wont-fix | **확인 — 해당 없음** | Round 1 | Celery 워커 전용 엔진 생성 지점은 없다 — 태스크는 `background_db_session`(= `background_engine`)을 쓰고 `worker_lifecycle` 은 기존 엔진의 `sync_engine.dispose` 만 한다. 스크립트(`create_superuser`)도 같은 세션 팩토리를 쓴다. |
