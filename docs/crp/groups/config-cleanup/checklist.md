# Checklist — config-cleanup (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] `git grep` 으로 세 묶음의 모든 참조 목록 작성 — app·scripts·migrations·CI·compose 에는 없음. `config.py`·`.env.example`·`tests/core/test_deployment_safety.py`·`README.md`·`docs/guides/ARCHITECTURE.md`·`docs/guides/workflows/server-lifecycle.html`, 과거 CRP 3곳(이력, 고치지 않음)
- [x] 모든 설정 클래스 `extra="ignore"` 확인, `python-multipart` 사용처 확인(`OAuth2PasswordRequestForm`, `admin_auth.py` 의 `request.form()`)

## Round 1 — 2026-10-19 REQ-001 — 완료 (브랜치 `chore/config-cleanup`)
- [x] (F-001) SMTP 삭제 + 배포 검사 항목·테스트 정리
- [x] (F-002) 업로드 설정 삭제
- [x] (F-003) `SESSION_EXPIRE_SECONDS` 삭제, README 세션·토큰 만료 표·업그레이드 노트, 다른 문서는 표를 가리킴
- [x] 계약 테스트 2건(사용 여부 + 예외 목록 낡음, 남은 키 무시), fail-on-revert(run-log)
- [x] ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), 게이트 docs·structure

## Round 2 — 2026-10-19 REQ-002 — 완료 (브랜치 `chore/config-cleanup-2`)
- [x] 현재 흐름 조사 — 콘솔 핸들러 생성 경로 4곳(앱 root `build_dictconfig`, `python main.py` 의 `setup_uvicorn_logging`, `uvicorn main:app` CLI 기본 핸들러 → `configure_logging`, Celery 워커 → `on_setup_logger`), 하드코딩 형식 위치(`LOG_FORMAT`·`access_fmt`·`TzFormatter.formatTime`)
- [x] (F-004) `API_VERSION`·`ApiSettings` 삭제, `.env.example`·문서·테스트, 남은 키 무시 테스트에 추가
- [x] (F-005) 형식·날짜·콘솔 on/off 연결, 전부 꺼짐 경고, 형식 검증, `.env.example` 주석·README 표·ARCHITECTURE §5·server-lifecycle 부록
- [x] 계약 테스트 예외 목록 삭제(INV-1 v0.2), 사용자 형식 마스킹 테스트(INV-7)
- [x] fail-on-revert(run-log Round 2)
- [x] ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), `-m mysql --collect-only`, review_gate 네트워크 없는 그룹, alembic 변경 없음

## Round 3 — 2026-10-19 REQ-003 (R-804) — 완료 (브랜치 `fix/uvicorn-access-log-format`)
- [x] 원인 확정 — 재현: `python main.py` 경로는 모든 접속 줄, `uvicorn main:app` 경로는 `?token=` 이 든 접속 줄에서 `--- Logging error ---`
- [x] (F-006) `TzAccessFormatter`, (F-007) 인자 단위 마스킹
- [x] 테스트 먼저(RED 6건), fail-on-revert(run-log Round 3)
- [x] ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), `-m mysql --collect-only`, review_gate 네트워크 없는 그룹, alembic 변경 없음
