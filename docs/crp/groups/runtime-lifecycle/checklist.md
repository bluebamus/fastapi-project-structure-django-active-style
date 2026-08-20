# Checklist — Runtime/Lifecycle (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔
> "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-08-19 (기준선) — 완료
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-001~008) + 이전 요구 충돌 확인
- [x] CRP 템플릿 복사 → `docs/crp/groups/runtime-lifecycle/` 6파일
- [x] 기준선 실측 — 621 tests / 22 paths·37 ops / alembic `d4e6f8b12c34` / review_gate 6그룹
- [x] 런타임 계층 전수 조사 — lifespan · 백그라운드 · 로깅 · Celery · 발견 부작용
- [x] 이월 결함 F-016~F-020 인수(원 번호 유지)
- [x] 신규 F-021 식별 — drain 이 미완료 태스크를 버린다
- [x] ADR-001~007 확정 · 불가침 제약 C-1~C-6 확립
- [x] **STOP: design-baseline + charter 승인** — 사용자 승인 완료(ADR-005 는 REQ-009 로 확정)

## Round 1 — 2026-08-19 (구현) — 완료
- [x] (F-016) `app/core/resources.py` — 등록 역순 정리·부분 실패 내성·단일 deadline (INV-1·2·11)
- [x] (F-016) `dispose_engine()` 부분 실패 내성 — 앞이 실패해도 뒤가 돈다
- [x] (F-021) `BackgroundTaskRunner` — admission 종료·예외 소비·cancel·재await·집합 비우기 (INV-3·4)
- [x] (F-017) `QueueHandler`/`QueueListener` — 파일 I/O 를 loop 밖으로, bounded + 드롭 카운터 (INV-5)
- [x] (F-017) bootstrap 1회 보장 + uvicorn 이 root 를 재정의하지 않음을 고정 (INV-6)
- [x] (F-018) SQL noise filter + `LOG_SQL_ECHO_ENABLED` (INV-7)
- [x] (F-018) staging/production 에서 opt-in 이면 기동 실패 (INV-8)
- [x] (F-020) `discover()` 부작용 0 + `install_hooks()` → `apps.ready()` (INV-9)
- [x] (F-019) Celery prefork 신호 — `close=False` 로 상속 pool 폐기·멱등 shutdown (INV-10)
- [x] 각 Fix 에 회귀 테스트 + fail-on-revert 검증(자원 관리자 내성 제거 시 2건 실패 확인)
- [x] C-1 기계 검증 — ORM/Raw Base·예제 기능 경로 diff 0
- [x] GATE 3 인수기준 전부 그린 — review_gate 6그룹 + 677 passed(skip 0)
- [x] `orm-raw-repository/ledger.md` 의 F-016~F-020 을 **Closed** 로 전환 → 그 그룹도 Open Fix 0
- [x] run-log 심각도 추세 갱신 + 수렴 판정 `CONVERGED`
- [x] residual-risk 갱신 (R-101~R-104)

## Round 2 — 2026-08-20 (R-105 결정 반영) — 완료
- [x] 사용자 결정 기록 — startup DDL 유지, 초기 개발 자동 생성 → 이후 Alembic 강제
- [x] README `### 4-1. 스키마 관리 — 자동 생성에서 Alembic 으로` 추가 (전환 시점·절차·함정)
- [x] "처음부터 Alembic" 경로 확인 및 명시 — `create_all` checkfirst 라 선적용 시 no-op
- [x] `main.py` 자동 생성 호출 지점에 정책 주석 (전환 후 새 모델 함정 · 다중 worker)
- [x] DEBUG 동작표에서 스키마 절로 링크
- [x] 회귀 테스트 1건 — README·주석 **양쪽**의 존재를 고정
- [x] fail-on-revert 검증 (한쪽을 지우면 1건 실패)
- [x] 게이트: 702 passed / review_gate 6그룹 / 라우트·alembic 불변
- [x] residual-risk R-105 를 Accept(사용자 결정)로 전환

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
