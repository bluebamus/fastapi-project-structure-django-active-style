# Checklist — Docs Learnability (개선 항목 추적판)

## Round 0 — 2026-08-20 (검수) — 완료
- [x] 요청을 design-baseline §2 에 기록 (REQ-001)
- [x] CRP 템플릿 복사 → `docs/crp/groups/docs-learnability/`
- [x] 학습자 경로 추적 — 최상위 → README → docs → 예제 코드
- [x] 두 학습 목표별 달성 여부 판정 (① 달성 / ② 미달성)
- [x] F-201~F-205 등록

## Round 1 — 2026-08-20 (배선) — 완료
- [x] (F-201) `docs/guides/orm-raw-workflow.md` — 선택 기준·파일 순서·결과 API·MySQL 검증
- [x] (F-201) README `## ORM / Raw 데이터 접근` 섹션 + 목차 항목
- [x] (F-202) README 제목을 실제 저장소명으로
- [x] (F-203) `docs/README.md` 진입점 — 읽는 순서 + 폴더별 성격
- [x] (F-204) `08-data-runtime-workflow` 현행화
- [x] (F-205) `pyproject.toml` name + 생성기 출력 안내
- [x] (ADR-002) `tests/test_docs_learnability.py` 21건 — 학습 경로를 테스트로 강제
- [x] fail-on-revert 검증 (제목·링크 되돌리면 2건 실패)
- [x] C-1 기계 검증 — 애플리케이션 동작 코드 diff 0
- [x] 게이트: 698 passed / review_gate 6그룹 / 라우트·alembic 불변
- [x] residual-risk 기록 (R-201~R-203)
- [x] run-log 수렴 판정 `CONVERGED`

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
