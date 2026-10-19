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

### 2-2. 비목표
- `API_VERSION`·`LOG_CONSOLE_*`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 정리(별도 결정 — residual-risk R-801).
- `python-multipart` 제거(사용 중 — `OAuth2PasswordRequestForm`, `admin_auth.py` 의 `request.form()`).
- 과거 CRP 그룹 문서 수정(append-only).

## 3. 인수 기준 (Acceptance Criteria)

- [x] 새 테스트 fail-on-revert 확인(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽.
- [x] `-m mysql --collect-only` 수집 확인.
- [x] `scripts/review_gate.py` 의 `docs`·`structure` 그룹 통과.
- [x] alembic 리비전 추가 없음.

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성.
