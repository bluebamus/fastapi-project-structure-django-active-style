# Checklist — orm-raw-repository (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다.
> ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-08-18 (Phase 0: 기준선, 코드 무변경)
- [x] 이번 요청을 design-baseline §2(REQ-002)에 기록 + 이전 요구(REQ-001) 충돌 확인 — 충돌 없음
- [x] CRP 그룹 6파일 적재 (`_template` 복사 후 작성)
- [x] 기준선 artifact 생성 — `baseline/{env.txt,pytest.txt,survey.txt,openapi.json}`
- [x] 결함 ledger 착수 — F-001 ~ F-007 등록(전부 코드 위치 확인 완료)
- [x] residual-risk 착수 — R-001 ~ R-007 등록
- [x] run-log Round 0 기록 + 수렴 판정(NOT CONVERGED)
- [ ] **STOP: Phase 1 착수 승인** — 여기서부터 런타임 코드가 바뀐다
- [ ] Phase 0 커밋 (`docs(crp): orm-raw-repository 그룹 기준선 확립`) — 사용자 승인 후

## 예정 — Phase 1 (Runtime/lifecycle hardening, 독립 커밋)
- [ ] (ledger F-001) `create_db_tables()` 재-discovery 제거, 동일 registry metadata 재사용 — discovery 호출 횟수 테스트
- [ ] (ledger F-006) staging/production 무인증 `/admin` fail-fast + `ADMIN` lazy import
- [ ] (residual R-007→해소) SQL/driver 로그 redaction, Alembic logger 보존, sentinel 비노출 테스트
- [ ] 경량 feature `__init__.py`, resource manager, drain, Celery 종료 경계
- [ ] `/ready` 추가 → 라우트 인벤토리 **19 paths / 31 operations** 로 갱신·고정
- [ ] Phase 1 게이트: pytest / ruff / format / mypy / bandit / alembic heads 전량 그린

## 예정 — Phase 2 이후
- [ ] Phase 2 (F-003) 설정 무관 read-only DML guard + 정식 Dependency 이름(기존 이름은 alias 유지)
- [ ] Phase 3 (F-002) ORM mixin·PK generic, `_get()` str 변환 제거
- [ ] Phase 4 ORM Repository 최소 CRUD·입력 불변성·EXISTS·예외 변환
- [ ] Phase 5 (F-007) `compose.test.yaml` + CI MySQL service, Alembic chain up/down/re-up smoke
- [ ] Phase 6 Raw Base — one/all/scalar/rowcount·binding·query name·예외·read-only 계약
- [ ] Phase 7 catalog(ORM) 예제 자동배선
- [ ] Phase 8 reports(Raw) 예제 자동배선
- [ ] Phase 9 (F-004, F-005) OpenAPI/문서 정리 + `scripts/review_gate.py` + 최종 인벤토리 22/37

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
