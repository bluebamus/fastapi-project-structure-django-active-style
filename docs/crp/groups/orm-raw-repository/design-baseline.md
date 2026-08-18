# Design Baseline — orm-raw-repository (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-08-18 · 변경 이력:
- 2026-08-18: 최초 선택 = 보통. 사유 — `docs/orm-raw-repository/2026-08-13/` 의 요구명세·개발계획·
  워크플로 지침 3종이 이미 확정 설계 문서로 존재하여 기획(P)·설계(D) 대부분이 선행 확정됨.
  남은 질문은 Phase 경계·비가역 작업(커밋/푸시) 승인에 한정한다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

FastAPI 워크플로우와 Django 스타일 `AppRegistry` 자동 발견·결선을 유지한 채, SQLAlchemy ORM 기반
데이터 접근과 `text()` 기반 Raw SQL 데이터 접근을 **Repository 구현만 다른 두 계층**으로 고도화한다.
DI·Service·세션 선택·트랜잭션 경계·검증·라우터 구성·문서·예외·테스트 기준은 두 방식이 동일해야 한다.
근거 문서는 `docs/orm-raw-repository/2026-08-13/` 의 requirements / development-plan / workflow-guide 3종이다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-13 | default-structure 저장소의 `docs/orm-raw-repository/2026-08-13/` 문서를 이 프로젝트 docs 에 같은 경로로 복사 | 설계·계획 문서 3종을 이 저장소 기준선으로 반입 | Active | 문서 3종(untracked) |
| REQ-002 | 2026-08-18 | "docs/orm-raw-repository/ 문서는 설계 및 개발계획서다. 이를 참고로 작업을 진행해줘" | 계획서 Phase 0~9 를 **독립 게이트·독립 커밋**으로 순차 실행. 이번 라운드는 Phase 0(기준선 확정, 코드 무변경)까지. | Active | ADR-001 · run-log Round 0 · ledger F-001~F-007 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-18 | Phase 0~9 를 순차 진행하되 각 Phase 를 독립 게이트·독립 커밋으로 분리한다. runtime/lifecycle(Phase 1) 과 ORM/Raw(Phase 3~8) 는 서로 섞지 않는다. | development-plan §10. 회귀 원인 분리와 롤백 단위 확보. | Accepted | — |
| ADR-002 | 2026-08-18 | ORM Base 와 Raw Base 는 서로 상속하지 않는다. 세션·예외·로깅 정책만 공유한다. | development-plan §1. 만능 Base 통합은 두 접근의 계약을 오염시킨다. | Accepted | — |
| ADR-003 | 2026-08-18 | 신규 기능은 `app/features/*` 규약 자동 발견으로만 결선한다. `main.py` 에 기능별 `include_router()` 를 추가하지 않는다. | development-plan §12 비목표. Django 스타일 자동배선이 이 저장소의 정체성. | Accepted | — |
| ADR-004 | 2026-08-18 | SQL 은 Repository 만 소유하고, commit 은 쓰기 View 가 성공 응답 전에 정확히 한 번 수행한다. | workflow-guide §1·§7. 트랜잭션 경계 단일화. | Accepted | — |
| ADR-005 | 2026-08-18 | SQLAdmin 에 인증 백엔드를 붙이지 않는다(**영구 비목표**). `ADMIN` 기본값 True 도 의도된 개발 편의 기본값으로 유지한다. 무인증 `/admin` 에 대한 방어선은 "인증 추가" 가 아니라 **staging/production 기동 거부(fail-fast)** 로 둔다. | 선행 확정 결정(2026-08-12, `config.py` ADMIN 필드 주석)을 그대로 승계한다. Phase 0 에서 이 결정을 모르고 F-006 을 "인증 백엔드 주입" 으로 적었다가 요구사항 회귀가 될 뻔했다. | Accepted | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: `main.py` 에 기능별 `include_router()`/중앙 router·Admin 목록을 추가하지 않는다 — ADR-003 에서 비롯.
- C-2: SQL 실행은 Repository 계층만 수행한다. View/Service 는 SQL 을 갖지 않고, Repository/Dependency 는 commit 하지 않는다 — ADR-004 에서 비롯.
- C-3: 기존 271 tests 와 18 paths / 30 operations 골든 인벤토리는 보존한다. 기존 자동배선 테스트를 삭제하거나 느슨하게 만들지 않는다 — REQ-002 에서 비롯.
- C-4: 전체 suite 의 skip / xfail / deselected 는 0 이다. MySQL marker 가 전부 skip 된 초록 결과는 실패로 처리한다 — development-plan §10.
- C-5: SQL / driver / ORM / commit / Alembic 로그와 오류 응답에 sentinel secret, SQL 원문, params, DSN 이 노출되지 않는다 — development-plan §13.
- C-6: 사용자 입력을 Raw SQL 문자열에 보간하지 않는다. 바인딩 파라미터만 사용한다 — workflow-guide §6.
- C-7: ORM Base 와 Raw Base 는 상속 관계를 갖지 않는다 — ADR-002 에서 비롯.
- C-8: SQLAdmin 에 인증 백엔드를 추가하지 않는다. `ADMIN` 기본값을 "보안 기본값" 명목으로 False 로 되돌리지 않는다. 대신 staging/production 에서 `ADMIN=true` 면 기동을 거부한다 — ADR-005 에서 비롯.
- C-9: 기능 패키지 `__init__.py` 는 라우터·모델·DB 모듈을 import 하지 않는다(초기화 훅 제외). 발견과 결선을 분리한 상태를 유지한다 — Phase 1 에서 비롯.

## 5. 변경 이력
- v0.1 (2026-08-18): 최초 작성. REQ-001/002, ADR-001~004, C-1~C-7 확정. Phase 0 기준선과 연결.
- v0.2 (2026-08-18): Phase 1 수행 중 선행 확정 결정(2026-08-12 Admin 인증 영구 비목표)을 발견해 ADR-005·C-8 로 승계. 패키지 init 경량화 계약을 C-9 로 고정.
