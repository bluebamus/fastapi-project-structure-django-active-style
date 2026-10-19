# Charter — config-cleanup  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)과 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 설정 | `config.py` | 소스 | `SMTPSettings`·`UploadSettings` 클래스·팩토리·싱글턴 삭제, `SessionSettings.SESSION_EXPIRE_SECONDS` 삭제, `validate_deployment_safety` 의 `SMTP_PASSWORD` 항목 삭제 |
| 예시 설정 | `.env.example` | 설정 | SMTP 절·업로드 절·`SESSION_EXPIRE_SECONDS` 줄 삭제 |
| 테스트 | `tests/core/test_settings_contract.py`(계약 2건 추가), `tests/core/test_deployment_safety.py`(SMTP 항목 삭제) | 테스트 | |
| 문서 | `README.md`(빠른 시작 표·환경 설정·세션·토큰 만료 표·업그레이드 노트·운영 배포·인증 흐름·CRP 목록), `docs/guides/ARCHITECTURE.md`(§4.2·§4.3·배포 게이트·§10 설정 표·§14), `docs/guides/server-lifecycle-guide.html`, `docs/guides/admin-auth-guide.html` | 문서 | |

- 기준선: base `ad59b1f`(main) · alembic head `a7c3e9f1b2d4`(변경 없음).

**v0.2 추가 인벤토리 (REQ-002, 브랜치 `chore/config-cleanup-2`, base `b32e106`)**

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 설정 | `config.py` | 소스 | `ApiSettings`(`API_VERSION`)·`get_api_settings`·`api_settings` 삭제. `LogSettings` 형식 기본값을 기존 하드코딩 형식으로, 형식·날짜 validator 추가 |
| 로깅 | `app/utils/logs/config.py`·`setup.py`·`formatters.py`, `app/celery/worker_lifecycle.py` | 소스 | 형식·날짜·콘솔 on/off 연결, `console_enabled()` 단일 판단, `adopt_external_handlers()`, 전부 꺼짐 경고 |
| 예시 설정 | `.env.example` | 설정 | API 절 삭제, 로그 키 주석을 실제 동작대로 |
| 테스트 | `tests/utils/test_log_settings_wiring.py`(신규), `tests/utils/test_log_redaction.py`(사용자 형식 마스킹 1건), `tests/core/test_settings_contract.py`(예외 목록 삭제·`API_VERSION` 무시) | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`(§4.2·§5·§14), `docs/guides/DEVELOPMENT.md`, `docs/guides/feature-development-guide.html`, `docs/guides/server-lifecycle-guide.html` | 문서 | |

## 2. 계약 (Contract)

### 2-1. 불변식 (Invariants)
- INV-1: `config.py` 의 모든 설정 필드는 app·scripts·migrations·`main.py`·`config.py` 어딘가에서 속성 접근(`.X`) 또는
  `getattr(…, "X")` 로 읽힌다. 예외는 테스트 안 `UNUSED_FIELD_EXCEPTIONS` 에 사유와 함께 둔다(현재 `API_VERSION`·
  `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` — 기존 문서가 이미 "선언만" 이라 적은 것).
  예외 목록이 낡아도(읽히게 되거나 사라지면) 실패한다.
  (검사: `tests/core/test_settings_contract.py::test_every_setting_field_is_read_somewhere`)
- INV-2: 지운 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS` 가 환경 변수·`.env` 에 남아 있어도 모든 설정 클래스가 오류 없이
  만들어지고 그 속성이 없다(모든 클래스 `extra="ignore"`). 기동을 거부하지 않는다.
  (검사: `test_removed_settings_are_ignored_when_left_in_environment`)
- INV-3: 배포 안전 검사는 그대로 동작한다 — `MYSQL_PASSWORD`(빈 값 포함)·`REDIS_PASSWORD`(값이 있을 때) placeholder 거부.
  (검사: `tests/core/test_deployment_safety.py` 비밀번호 절)
- INV-4: 세션·토큰 만료의 정본은 README `세션·토큰 만료` 표 하나이고, 다른 문서는 그 표를 가리킨다.

- INV-1 (v0.2 개정, REQ-002): 예외 목록 `UNUSED_FIELD_EXCEPTIONS` 는 없다 — 읽히지 않는 필드가 하나라도 있으면 실패한다.
- INV-2 (v0.2 확장): `API_VERSION` 도 남아 있으면 무시된다(같은 테스트의 `REMOVED_SETTINGS`).
- INV-5: `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 은 실제 출력 줄을 정하고 기본값은 기존 하드코딩 형식과 같다
  (앱 root 콘솔·파일, `setup_uvicorn_logging()`). 잘못된 형식·빈 날짜 형식은 설정 오류.
  (검사: `tests/utils/test_log_settings_wiring.py`)
- INV-6: `LOG_CONSOLE_ENABLED=false` 면 콘솔 핸들러를 만드는 모든 경로(앱 root·`setup_uvicorn_logging()`·uvicorn CLI·Celery 워커)에
  콘솔 핸들러가 0개이고 파일 핸들러는 그대로다. 판단은 `console_enabled()` 한 곳. 출력이 모두 꺼지면 stderr 경고 한 줄.
- INV-7: 비밀값 마스킹은 사용자 형식에서도 유지된다(`test_masking_holds_with_user_log_formats`).
- INV-8 (v0.3, REQ-003): uvicorn 접속 레코드(args 5개)는 `python main.py`·`uvicorn main:app` 두 경로 모두 logging 오류 없이
  요청 라인으로 찍히고, 쿼리의 비밀값은 가려지며, `python main.py` 경로는 시간대·`LOG_DATE_FORMAT` 을 따른다.
  (검사: `tests/utils/test_log_redaction.py` 의 접속 줄 절)

### 2-2. 비목표
- `API_VERSION`·`LOG_CONSOLE_*`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 정리(별도 결정 — residual-risk R-801).
- `python-multipart` 제거(사용 중 — `OAuth2PasswordRequestForm`, `admin_auth.py` 의 `request.form()`).
- 과거 CRP 그룹 문서 수정(append-only).
- (v0.2) uvicorn CLI·Celery 워커가 스스로 세운 콘솔 핸들러의 **형식** 변경 — 기본 출력 유지(R-803).
- (v0.2) `setup_uvicorn_logging()` access 포매터의 요청 라인 필드 결손(R-804, 이번 변경 전부터 있음).

## 3. 인수 기준 (Acceptance Criteria)

- [x] 새 테스트 fail-on-revert 확인(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽.
- [x] `-m mysql --collect-only` 수집 확인.
- [x] `scripts/review_gate.py` 의 `docs`·`structure` 그룹 통과.
- [x] alembic 리비전 추가 없음.

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성.
- v0.2 (2026-10-19): REQ-002 — 인벤토리 추가, INV-1 개정, INV-5~7, 비목표 2건. 비목표의 R-801 항목은 REQ-002 로 해소.
- v0.3 (2026-10-19): REQ-003 — R-804 해소. INV-8 추가, 비목표의 R-804 항목은 해소.
