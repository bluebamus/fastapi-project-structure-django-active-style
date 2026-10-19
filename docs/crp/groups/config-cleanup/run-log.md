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
