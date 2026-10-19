# Checklist — admin-session-hardening (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 확인 — security-ops-hardening R-601·R-602·R-606, admin-login R-301·R-302 에 상태 주석, log-redaction-fixes 에 R-408(405 사용자 결정) append
- [x] CRP 6파일 작성, 기준선 확인(main `ca7973c`, alembic head `a7c3e9f1b2d4`)
- [x] sqladmin 0.32 소스·템플릿·`statics/js/main.js` 조사 — 상태 변경 요청 목록(생성·수정 폼 POST, 삭제·일괄 삭제 `$.ajax` DELETE, 가져오기 `fetch`, 로그아웃 GET 링크, 사용자 정의 action GET), 템플릿 로더(`sqladmin_original` 접두사), `head_tail` 을 덮어쓰는 원본 화면 없음, 필터 객체 `template` include
- [x] 폐기 지점 조사 — `UserService.update_user`(비활성화·강등)·`delete_user` 가 `revoke_user` 를 부른다. 비밀번호 변경 경로 없음(F-005)
- [x] `itsdangerous` 소비처 조사 — 서명 쿠키 테스트 헬퍼뿐(starlette `SessionMiddleware` 를 더는 쓰지 않음)

## Round 1 — 2026-10-19 REQ-001 — 완료
- [x] (F-001) `AdminSessionStore`·`RedisSessionMiddleware`·`rotate_session`, `get_admin_session_store`, `ADMIN_SESSION_*` 설정·검증, `UserService` 폐기 훅, `itsdangerous` 제거
- [x] (F-002) `AdminCsrfMiddleware`(헤더·폼 본문 버퍼링+재생)·`csrf_valid` 공유, `base.html` 덮어쓰기(meta·스크립트), POST 전용 로그아웃, 로그인 시 토큰 회전
- [x] (F-003) `LocalDateFilter` 연산 `range`·`range_bounds`·`quick_ranges`, 전용 필터 템플릿
- [x] (F-004) 405 `Allow` 현행 유지 — ADR-006, R-706, log-redaction-fixes R-408
- [x] 모든 문서 반영 — README(기능·환경 표·운영 확인 2b·관리 화면 절·문제 해결·CRP 목록)·ARCHITECTURE(§4·§10.3·§10.4·§14)·DEVELOPMENT(§9·§12)·admin-auth-guide.html(세션 구조·시퀀스·쿠키/Redis 키 표·만료·CSRF 흐름·위협 모델·문제 해결)·server-lifecycle-guide.html·CRP
- [x] fail-on-revert(run-log), ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론), 게이트, 실기동 스모크
## Round 2 — 2026-10-19 REQ-002(R-705 해소) — 완료 (브랜치 `fix/admin-ui-revoke`)
- [x] sqladmin 0.32 훅 확인 — `_queries.py` 의 수정(`on_model_change` → 값 반영 → 커밋 → `after_model_change`)·삭제(`on_model_delete` → 커밋 → `after_model_delete`) 순서, `application.py` 의 edit·delete 가 훅 예외를 삼킴
- [x] (F-007) `UserAdmin.on_model_change`·`after_model_change`·`after_model_delete`, `loses_admin_access`, `revoke_user_sessions`·`session_store_of`, 실패 표시 → 503, 기존 세션 저장 `SET XX`
- [x] 문서 — admin-auth-guide 폐기 표·설명, README 관리 화면 절, CRP append(ADR-007, F-007, R-705 해소), docs/review 상태
- [x] fail-on-revert(run-log Round 2), ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론)
## Round 3 — 2026-10-19 REQ-003(커밋 전 폐기·refresh 포함) — 완료 (브랜치 `fix/admin-ui-revoke-precommit`)
- [x] sqladmin 0.32 `_queries.py` 확인 — `on_model_change`·`on_model_delete` 는 세션 안, commit 앞에서 불린다(예외 = 커밋 없음·롤백). `application.py` 의 edit·delete 는 그 예외를 400 폼·목록 `error` 로 그린다
- [x] (F-010) R-707 결정 — 판정 `revocation_for`·폐기 `revoke_user_access` 를 `user_service.py` 한 곳으로, `UserService.update_user`·`delete_user` 도 사용, 강등도 refresh 폐기(ADR-010), API 비활성화의 family 폐기를 직접 보는 테스트 추가
- [x] (F-009) 감독자 정정 — `revocation_for` 하나가 두 집합(관리 세션·refresh)을 돌려주고 강등은 관리 세션만, `revoke_user_access` 는 `None` 쪽 건너뜀, API `UserService` 불일치는 R-707
- [x] (F-008) `UserAdmin.on_model_change`·`on_model_delete` 로 이동, `revoke_user_access`(refresh + 관리 세션) 공유, `AdminSessionStore.redis`, 503 변환 장치 제거, 변경 전후 비교·`SET XX` 유지
- [x] 문서 — admin-auth-guide 실패 경로·폐기 표·설명, README, ARCHITECTURE, CRP append(ADR-007 Superseded → ADR-008, F-008, R-705 개정), docs/review 상태
- [x] fail-on-revert(run-log Round 3), ruff·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 클론)
