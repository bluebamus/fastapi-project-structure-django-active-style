# Checklist — service-hardening (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다. 단계 하나 = Round 하나.

## Round 0 — 2026-10-12 (계획)
- [x] 이번 요청을 design-baseline §2 에 기록(REQ-001) + 이전 요구 충돌 확인 — orm-raw-repository charter 2-4·R-002 를 ADR-018 로 대체, 그 그룹 design-baseline 에 상태 주석 append
- [x] CRP 템플릿 6파일 작성, 기준선 실측(814 passed / 32 deselected / skip 0)
- [x] 2026-10-07 리뷰 지적을 ledger F-001~F-023 으로 등록, 범위 밖 항목은 residual-risk 로

## Round 1 — 2026-10-12 단계 A (CI 재현성 · DSN · 잠금 읽기 · 정렬) — 완료
- [x] (F-001) CI 두 job `uv sync --locked`, 주석 정정 + 계약 테스트
- [x] (F-002) 게이트 파일 목록 = `git ls-files -z`(git 없을 때만 순회) + 추적되지 않은 파일 제외 테스트
- [x] (F-003) DSN `URL.create`·마스킹 `render_as_string`·Alembic `%%`·Redis 비밀번호 인코딩 + 왕복 테스트, 문자열 비교 테스트를 URL 의미 비교로
- [x] (F-004) 잠금 읽기 = 쓰기(라우터 on/off), read-only 거부 + 테스트
- [x] (F-005) `get_all` 기본 정렬 + PK 보조 키, 결정적 순서·겹치지 않는 페이지 테스트
- [x] 문서 정정 — `docs/guides/ARCHITECTURE.md` §8.3 라우팅 규칙·Alembic URL, `docs/guides/DEVELOPMENT.md` §5.3·§6.5, `docs/guides/feature-development-guide.html` 의 "정렬 없음"
- [x] 각 Fix fail-on-revert 확인, GATE 3 그린(845 passed / 32 deselected / skip 0), run-log 기록

## Round 2 — 2026-10-12 단계 B (접속 로그 · 오류 매핑) — 완료
- [x] (F-006) `ClientIPResolver` + `TRUSTED_PROXY_HOPS`(옛 `TRUST_PROXY_HEADERS` 대체, ADR-019), 미들웨어 생성자 주입
- [x] (F-008·F-009·F-010) 미들웨어 500 기록·민감 query 가림·쿠키 이름 설정 (F-008 의 조회 접근 통제는 Round 7)
- [x] (F-007) home 기능에서 컬럼 길이 절단(모델에서 도출)
- [x] (F-011) Update 스키마 null 거부(`PatchSchema`) + DB 오류 코드별 변환(`DBErrorTranslator`, delete 포함)
- [x] (F-012) 리포트 기간 상한, (F-013) 4xx 로그 레벨
- [x] 문서 — `.env.example`·README 환경표/배포 체크·ARCHITECTURE §4·§7.1·§9·§10.3·DEVELOPMENT §5.1·§5.3·§6·가이드 HTML 2종·Home 태그 설명
- [x] 각 Fix fail-on-revert 확인, GATE 3 그린(905 passed / 32 deselected / skip 0), run-log 기록

## Round 3 — 단계 C (테스트 하네스)
- [ ] (F-014) 공용 override 헬퍼로 전 엔드포인트 테스트 전환 + read-only flush 거부 회귀
- [ ] (F-015) MySQL ORM 스모크(`mysql` 마커, 로컬은 수집만 확인)

## Round 4 — 단계 D (UTC 저장)
- [ ] (F-016) `UTCDateTime`·Alembic 리비전·리포트 영업일 집계·Celery `enable_utc`
- [ ] TypeDecorator 단위·마이크로초 보존·응답 오프셋 테스트, MySQL 왕복(`mysql` 마커)

## Round 5 — 단계 E (Redis 필수 · /ready · Celery 발견)
- [ ] (F-017) `get_redis` provider, `/ready` DB+Redis 503
- [ ] (F-018) 기능별 tasks 모듈 + registry 기반 include, 기능 제거 내성 테스트

## Round 6 — 단계 F1 (인증 코어)
- [ ] (F-019·F-020·F-021) `PasswordHasher`·`TokenService`·`RefreshTokenStore`·`RateLimiter`·`AuthService` 주입, 엔드포인트 register/login/refresh/logout/me
- [ ] 해시 이전·claims 거부·회전·재사용 탐지·429 테스트(fakeredis)

## Round 7 — 단계 F2 (인가 · 소유권 · 운영 도구)
- [ ] (F-022·F-023·F-008) `Principal`·`get_current_principal`·`OwnershipPolicy`·슈퍼유저 경로, 작성자 컬럼 리비전
- [ ] 슈퍼유저 생성 스크립트, 문서·`.env.example`·라우트 인벤토리 갱신
- [ ] 401·403·소유자·슈퍼유저 우회·비활성화 refresh 실패·접속 로그 user_id 테스트

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
