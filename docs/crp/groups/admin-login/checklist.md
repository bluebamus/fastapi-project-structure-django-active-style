# Checklist — admin-login (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-12 (계획)
- [x] 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 충돌 확인 — service-hardening ADR-017·C-9·R-203, orm-raw-repository C-8 을 ADR-002 로 대체, 각 문서에 상태 주석 append
- [x] CRP 6파일 작성, 기준선 확인(main `7a99987`, 1098 passed / 42 deselected / skip 0)

## Round 1 — 2026-10-12 REQ-001 (관리 로그인·배포 전 확인) — 완료
- [x] (F-001) `AdminAuthBackend` + `verify_credentials` 공유 + `create_admin_interface` 주입 + `itsdangerous`
- [x] (F-001) 세션 쿠키 속성·세션 고정 방지·매 요청 DB 확인·로그아웃
- [x] (F-001) rate limit(`admin:rl:`, 429 + `Retry-After`)·로그(비밀번호 없음, 사용자명 64자)
- [x] (F-001) Bootstrap 5.3.8 로그인 화면(SRI 실측 계산), 템플릿 로더 우선순위 확인
- [x] (F-002) 무인증 확인 플래그·배포 게이트 규칙·기동 WARNING 제거, 남은 키 무시 회귀
- [x] (F-004) Celery include import 테스트
- [x] (F-005) 배포 전 확인 4항목 — README 체크리스트·환경표·빠른 시작·문제 해결, `.env.example`, config Field, `ClientIPResolver`, 리비전 docstring, 스크립트·조립 지점 docstring
- [x] 통합(create_superuser → 로그인 흐름)·`mysql` 마커 테스트(수집 확인)

## Round 2 — 2026-10-12 REQ-002 (ADMIN_DISABLED·세션 범위·가이드·전 문서) — 완료
- [x] (F-003) `ADMIN` → `ADMIN_DISABLED`, `validate_renamed_settings`, 기존 테스트·기능 docstring·생성기 템플릿 갱신
- [x] (F-003) `ADMIN_DISABLED=true` 보장 4가지 테스트(404·응답/헤더·기동 로그·미들웨어)
- [x] 세션 범위 확인(감독자 가정과 일치) + 테스트 4건
- [x] `docs/guides/admin-auth-guide.html`(12절·도식 8개) + 문서 계약 테스트 등록 + README 문서 표·ARCHITECTURE §10.3 링크
- [x] (F-007) 모든 문서 반영 — README·`.env.example`·ARCHITECTURE·HTML 가이드 2종·CRP(이 그룹, service-hardening, orm-raw-repository 상태 주석)
- [x] 실제 기동 스모크, 낡은 서술 grep 확인(run-log)
- [x] (F-006) 기존 ModelView `column_filters` 의 sqladmin 0.32 비호환 — Round 3 에서 처리

## Round 3 — 2026-10-12 REQ-003 (감독자 결정: 목록 필터·리비전 체인) — 완료
- [x] (F-006) 5개 ModelView 필터를 `sqladmin.filters` 클래스로, `created_at` 필터 제외(ADR-011)
- [x] 등록된 모든 ModelView 목록(필터마다 쿼리 1건)·상세 1건 200 테스트 + 대조군(필터 14개 실행), fail-on-revert
- [x] 생성기 템플릿에 필터 예시 주석(템플릿은 필터를 생성하지 않는다)
- [x] (F-008) ARCHITECTURE §12 revision 체인 head
- [x] 기동 스모크로 7개 목록·필터 3건·상세 200 확인
