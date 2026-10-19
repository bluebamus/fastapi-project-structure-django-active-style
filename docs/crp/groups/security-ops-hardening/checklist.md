# Checklist — security-ops-hardening (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 확인 — admin-login R-302·R-310, log-redaction-fixes R-401·R-402, service-hardening R-201·R-204·R-211 에 상태 주석 append
- [x] CRP 6파일 작성, 기준선 확인(main `a1625fe`, 1190 passed / 43 deselected / skip 0 — access-policy 종료 기록)
- [x] 엔진 생성 지점 전수(`create_async_engine`·`create_engine`·`engine_from_config`): session.py 3곳 + Alembic 1곳, 모두 `hide_parameters` 없음
- [x] sqladmin 0.32 소스 확인 — GET 로그인 렌더는 컨텍스트 없음(`Admin.login`), 템플릿 엔진 `env.globals`, 연산 필터 프로토콜(`has_operator`·`get_filtered_query(query, operation, value, model)`)
- [x] Celery beat 가 시작 시 include 를 import 함 확인(`Beat.init_loader` → `loader.init_worker` → `import_default_modules`)

## Round 1 — 2026-10-19 REQ-001 — 완료
- [x] (F-001) `ENGINE_SAFETY_OPTIONS` — writer·reader·background·Alembic
- [x] (F-002) `ACCESS_LOG_RETENTION_DAYS`·`AccessLogRetentionService`·`delete_created_before`·provider·태스크·beat 03:30
- [x] (F-003) 로그인 폼 CSRF(템플릿 전역 `csrf_token`, 레이트 리밋 전 `compare_digest`, 403 재표시)
- [x] (F-004) `LocalDateFilter` + 7개 뷰, 스캐폴드 안내 주석
- [x] (F-005) 토큰 15분·권한 회수 지연 유지 — ADR-005, 이전 그룹 R-201·R-211 주석
- [x] 모든 문서 반영 — README(환경 표·운영 확인 8·beat 명령·관리 화면 절)·ARCHITECTURE(§5·§7.1·§8.1·§10.3·§10.4·§11·§14)·DEVELOPMENT §9·admin-auth-guide.html(로그인 시퀀스·실패 경로 도식·세션 값·위협 모델·확장 주의)·CRP
- [x] fail-on-revert(run-log), ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), 게이트 structure·supply·docs, 실제 기동 스모크
