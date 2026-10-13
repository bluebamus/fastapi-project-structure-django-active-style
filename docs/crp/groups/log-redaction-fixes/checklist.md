# Checklist — log-redaction-fixes (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-13 (계획·재현)
- [x] 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 확인 — orm-raw-repository R-007(traceback ceiling)을 이 그룹이 닫음, 상태 주석 append
- [x] CRP 6파일 작성, 기준선 확인(main `179bfe1`, 1140 passed / 43 deselected / skip 0 — admin-login 종료 기록)
- [x] 프로젝트 로깅 구성으로 traceback 노출 재현(console·파일·uvicorn — run-log)
- [x] DEBUG 500 `str(exc)` 경로 확인 — 없음(F-010)

## Round 1 — 2026-10-13 REQ-001 — 완료
- [x] (F-001) `RedactingFilter` 가 `exc_text`·`stack_info` 를 `redact()` 로 가림 — 경로별 테스트(development console·production console+파일·uvicorn log_config·uvicorn CLI·Celery)
- [x] (F-002) `Bearer` 규칙을 `redact()` 에
- [x] (F-003) `redact_handlers()` — `configure_logging()`(uvicorn 로거)·Celery 수신자
- [x] (F-004) `StarletteHTTPException` 핸들러가 `exc.headers` 를 싣는다 — 405 `Allow`·임의 헤더·본문 형식
- [x] (F-005) `REDIS_MIN_VERSION`·`check_redis_version()`·lifespan 연결, 계약 테스트, compose·`.env.example`·docstring
- [x] (F-009) 접속 로그 원문 저장 유지 — ADR-003·R-401, ARCHITECTURE §10.4 표시
- [x] 명세 §5 엔드포인트 보호 조사(읽기 전용) — 감독자 보고, R-406

## Round 2 — 2026-10-13 REQ-002 (커버리지 하한 0) — 완료
- [x] (F-006) `fail_under = 0` 명시, CI 단위 단계·`tests` 게이트 측정, 계약 테스트
- [x] (F-007) `--cov-config=pyproject.toml` — 서브프로세스 합치기 INTERNALERROR 해소
- [x] (F-008) not-yet-valid 토큰 테스트의 시간 의존 제거
- [x] 모든 문서 반영 — README(기술 스택·빠른 시작·테스트·환경 표·운영 체크리스트 4a·API 오류·문제 해결)·ARCHITECTURE(§3·§5·§6·§9·§10.4·§13·§14)·DEVELOPMENT(§9·§11)·HTML 가이드 2종·CRP
- [x] `.env` 없는 저장소 밖 클론에서 전체 suite(run-log)
