# Checklist — access-policy (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-13 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 확인 — log-redaction-fixes R-406(기본 거부 없음)을 이 그룹이 닫음, 상태 주석 append
- [x] CRP 6파일 작성, 기준선 확인(main `3880451`, 1166 passed / 43 deselected / skip 0 — log-redaction-fixes 종료 기록)
- [x] FastAPI 0.141 의 중첩 include 순회 확인 — `iter_route_contexts` 의 effective context 가 합친 경로·의존성 트리를 준다(실측)
- [x] 변경 전 `app.openapi()` 직렬화 확보(OpenAPI 불변 비교용)

## Round 1 — 2026-10-13 REQ-001 — 완료
- [x] (F-001) `app/core/security/access.py` — 접근 수준 4개·`AccessPolicyGuard`, `main.py` 조립 끝 `verify`
- [x] (F-002) 예시 뷰 전체 뷰 단위 선언, home·reports 라우터 단위 의존성 이동, `/health`·`/ready`·`/docs` `Public`, OpenAPI 바이트 동일
- [x] (F-003) `POLICY` → `EXPECTED` + 가드 판정·OpenAPI security 대조 테스트 1개, 401/403·소유권 실요청 테스트 유지
- [x] (F-004) 스캐폴드 예시 뷰(`dependencies=[Public]`)·안내문, 생성 결과가 가드를 통과하는 테스트
- [x] (F-005) `/docs` 는 `APIRoute` — 제외 목록 없이 `Public` 선언(해당 없음 처리)
- [x] 모든 문서 반영 — README(운영 체크리스트 6·권한 표)·ARCHITECTURE §10.2·DEVELOPMENT(§1·§7.1·§12)·HTML 가이드 2종·CRP
- [x] fail-on-revert(run-log), ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), 게이트 structure·supply·docs
