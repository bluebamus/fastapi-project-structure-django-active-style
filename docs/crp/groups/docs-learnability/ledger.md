# Ledger — Docs Learnability (결함 대장)

> ID 규칙: 이 그룹의 결함은 다른 그룹과 충돌하지 않도록 **F-201** 부터 매긴다.

| ID | 등급 | 위반 계약 | 처리 | 상태 | 내용 | 조치 |
|---|---|---|---|---|---|---|
| F-201 | HIGH | REQ-001 / INV-1·INV-3 (ORM/Raw 학습 경로) | Fix | **Fixed** | 학습자용 문서 3종(`README.md`·`QUICKSTART.md`·`ARCHITECTURE.md`)에 Raw SQL·`RawRepositoryBase`·catalog·reports 언급이 **각각 0건**이었다. README 는 `workflow-guide.md` 도 `docs/project-guide/` 도 한 번도 링크하지 않았다. 즉 1,206행 지침서와 두 완결 예제가 **존재하지만 도달 불가**였다. 사용자가 명시한 목표 두 개 중 하나가 통째로 미달성 상태. | Round 1. `docs/guides/orm-raw-workflow.md` 신규 작성(선택 기준·파일 순서·자주 틀리는 지점·결과 API 의미·MySQL 검증 절차) + README 에 `## ORM / Raw 데이터 접근` 섹션과 목차 항목 추가. 회귀: `tests/test_docs_learnability.py` — fail-on-revert 확인. |
| F-202 | MED | INV-2 (저장소 정체성) | Fix | **Fixed** | README 제목이 `# FastAPI Default Project Structure` — **다른 저장소(형제 repo)의 이름**이었다. 2026-08-12 기준선 교체(`f35a938`) 때 형제 저장소 스냅샷을 들여오며 남은 잔재. 학습자가 **가장 먼저 보는 한 줄**이 틀린 상태였다. | Round 1. `# FastAPI Project Structure — Django Active Style` 로 교체. 회귀 테스트가 이전 이름의 재유입도 막는다. |
| F-203 | MED | ADR-003 / INV-5 (문서 진입점) | Fix | **Fixed** | `docs/` 에 안내 문서가 없어 5개 하위 폴더 중 무엇부터 볼지 알 수 없었다. 특히 날짜가 박힌 두 폴더 중 **하나만 지금도 유효한 지침서**라는 사실이 어디에도 없었다 — 학습자가 "지난 기록" 으로 읽고 건너뛰는 것이 합리적인 상태였다. | Round 1. `docs/README.md` 신규 작성 — 읽는 순서, 폴더별 성격(살아 있는 문서 / 설계 기준선 / 검수 이력) 구분. |
| F-204 | MED | REQ-001 (문서 현행성) | Fix | **Fixed** | `docs/project-guide/v1.0.0/08-data-runtime-workflow` 가 "Raw SQL과 ORM 구현을 선택하는 구조는 **별도 계획이며 아직 런타임 선택 기능이 아니다**" 라고 서술. 08-18 작성이라 08-19 의 Raw 계층·예제를 모른다. 학습자가 이걸 읽으면 **Raw 계층을 찾아볼 이유 자체가 사라진다** — 없는 것을 찾지는 않는다. | Round 1. 갱신 주석으로 현행화하고 가이드·두 예제를 가리키게 했다. 원 문장은 작성 시점 기록으로 남기고 그 위에 갱신을 덧붙이는 형태 — 버전 문서라 통째로 고쳐 쓰지 않는다. |
| F-205 | LOW | INV-8·INV-9 (안내 일관성) | Fix | **Fixed** | ① `pyproject.toml` 의 `name` 이 `fastapi-default-project-structure` 로 F-202 와 같은 잔재. ② 생성기가 뼈대만 만들고 끝나 "다음에 무엇을 할지" 를 알려주지 않았다 — 이 구조에서 가장 먼저 정해야 하는 것이 ORM/Raw 선택인데 그 안내가 없었다. | Round 1. 패키지명을 저장소명과 일치시키고, 생성기 출력에 가이드·두 예제 경로를 추가했다(로직 불변, 출력 문구만). |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
