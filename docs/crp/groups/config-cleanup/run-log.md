# Run Log — config-cleanup (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지.

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `ad59b1f`) — 계획·조사
- **트리거:** 사용자 결정 REQ-001(SMTP·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS` 삭제, 기존 만료 설정을 정본으로).
- **조사:** 참조 목록은 checklist Round 0. 계약 테스트 시험 실행 — 속성 접근·`getattr` 만으로 미사용 필드는 세 묶음 외에 5건(R-801)뿐이라 오탐 없이 의미가 있다.
- **신규 finding:** LOW 3 (F-001~F-003)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 3)

### Round 1 — 2026-10-19 — REQ-001 구현 (브랜치 `chore/config-cleanup`)
- **Fix:** F-001·F-002·F-003 → **Fixed**. ADR-001~ADR-003.
- **동작이 바뀐 기존 테스트:** `tests/core/test_deployment_safety.py` — `_install` 의 `smtp_settings` 스텁 삭제, `test_empty_smtp_password_passes` 삭제, 비밀번호 거부 매개변수에서 SMTP 제거, 개발 환경 거부 사례 SMTP → REDIS, `.env.example` 복사 검사는 `MYSQL_PASSWORD` 만, 서브프로세스 환경의 `SMTP_PASSWORD` 제거.
- **DB·Redis 접속 없음.**

### fail-on-revert (Round 1)
대상 파일을 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\active\config-cleanup\`)에 복사해 두고 되돌린 내용을 넣어 돌린 뒤 복사본으로 복원했다(바이트 비교 동일).

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| `SessionSettings` 에 `UPLOAD_DIR` 필드 하나 되살림 | `test_every_setting_field_is_read_somewhere` | 실패(`['UPLOAD_DIR']`) — `test_every_config_field_is_documented_in_env_example`·`test_removed_settings_are_ignored_when_left_in_environment` 도 실패 |
| `config.py` 전체를 base(`ad59b1f`)로 | `test_every_setting_field_is_read_somewhere` | 실패(`SESSION_EXPIRE_SECONDS`·`SMTP_*`·`UPLOAD_*`) |
| 〃 | `test_removed_settings_are_ignored_when_left_in_environment` | 실패(`SESSION_EXPIRE_SECONDS` 에 정수가 아닌 값 → 검증 오류) |
| 예외 목록에 읽히는 필드(`SESSION_COOKIE_NAME`) 추가 | `test_every_setting_field_is_read_somewhere` | 실패(`UNUSED_FIELD_EXCEPTIONS 에서 지울 항목`) |

- **수렴 판정:** `CONVERGED` (Open Fix 0)

### Round 2 — 2026-10-19 (base SHA: `b32e106`) — REQ-002 구현 (브랜치 `chore/config-cleanup-2`)
- **트리거:** 사용자 결정 REQ-002("API_VERSION 삭제, 로그 설정은 실제로 연결") — R-801 해소.
- **조사(현재 흐름):** 콘솔 핸들러는 네 경로에서 생긴다 — ① `build_dictconfig()` 의 root `console`(stdout, `TzFormatter(LOG_FORMAT)`), ② `python main.py` 의 `setup_uvicorn_logging()`(`default`·`access` stdout, `LOG_FORMAT`·`access_fmt`), ③ `uvicorn main:app` CLI 가 앱 import 전에 세운 uvicorn 기본 핸들러(uvicorn 형식, `configure_logging()` 이 마스킹만 달았음), ④ Celery 워커가 root 를 가로채며 붙인 핸들러(Celery 형식, `on_setup_logger` 가 마스킹만). 하드코딩: `app/utils/logs/config.py` 의 `LOG_FORMAT`(앱·uvicorn default·파일 공용), `setup.py` 의 `access_fmt`, `TzFormatter.formatTime` 의 `%Y-%m-%d %H:%M:%S`(+development 밀리초). `LogSettings` 의 형식 기본값(`[{asctime}] {levelname:8} [{name}:…]`)은 실제 형식과 달랐다.
- **Fix:** F-004·F-005 → **Fixed**. ADR-004~ADR-007. 신규 잔여 위험 R-803(CLI·Celery 형식 미적용, 의도), R-804(access 포매터 필드 결손, 기존 결함).
- **동작이 바뀐 기존 테스트:** `tests/core/test_settings_contract.py` — `UNUSED_FIELD_EXCEPTIONS` 삭제, 미사용 필드 0 단언, `REMOVED_SETTINGS` 에 `API_VERSION`, 설정 클래스 수 하한 10 → 9.
- **DB·Redis 접속 없음.**

### fail-on-revert (Round 2)
테스트를 먼저 쓰고 구현 전 코드에서 돌렸다(RED): 새 테스트 20건 실패 — 기본값 1, 형식·날짜 출력 4, 콘솔 끔 4, 전부 꺼짐 경고 2, 형식 검증 6, 계약 2(미사용 필드·`API_VERSION` 무시). 구현 뒤 연결 코드만 되돌린 검사: `app/utils/logs/config.py`·`setup.py`·`formatters.py`·`app/celery/worker_lifecycle.py` 를 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\active\config-cleanup-2\revert\`)에 복사하고 `main` 판으로 바꿔 돌린 뒤 복사본으로 복원했다.

| 되돌린 것 | 결과 |
|---|---|
| 로깅 연결 4파일을 하드코딩 판(`main`)으로 | `test_log_settings_wiring.py` 10건 실패(형식·날짜 출력 4, 콘솔 끔 4, 경고 2). 설정 쪽 테스트(기본값·검증)는 `config.py` 가 그대로라 통과 — 이들은 구현 전 RED 로 확인 |
| 구현 전 코드 전체 | 위 20건 실패(RED) |

기본 출력 회귀(`test_default_settings_keep_previous_console_line`)·Celery 콘솔 켬·사용자 형식 마스킹은 변경 전에도 참인 보호 테스트라 되돌려도 통과한다(의도).

- **수렴 판정:** `CONVERGED` (Open Fix 0)
