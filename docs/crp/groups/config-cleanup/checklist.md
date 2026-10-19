# Checklist — config-cleanup (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] `git grep` 으로 세 묶음의 모든 참조 목록 작성 — app·scripts·migrations·CI·compose 에는 없음. `config.py`·`.env.example`·`tests/core/test_deployment_safety.py`·`README.md`·`docs/guides/ARCHITECTURE.md`·`docs/guides/server-lifecycle-guide.html`, 과거 CRP 3곳(이력, 고치지 않음)
- [x] 모든 설정 클래스 `extra="ignore"` 확인, `python-multipart` 사용처 확인(`OAuth2PasswordRequestForm`, `admin_auth.py` 의 `request.form()`)

## Round 1 — 2026-10-19 REQ-001 — 완료 (브랜치 `chore/config-cleanup`)
- [x] (F-001) SMTP 삭제 + 배포 검사 항목·테스트 정리
- [x] (F-002) 업로드 설정 삭제
- [x] (F-003) `SESSION_EXPIRE_SECONDS` 삭제, README 세션·토큰 만료 표·업그레이드 노트, 다른 문서는 표를 가리킴
- [x] 계약 테스트 2건(사용 여부 + 예외 목록 낡음, 남은 키 무시), fail-on-revert(run-log)
- [x] ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), 게이트 docs·structure
