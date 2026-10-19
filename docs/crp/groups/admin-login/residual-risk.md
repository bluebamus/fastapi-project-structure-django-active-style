# Residual Risk — admin-login (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-301 | **해소(2026-10-19, admin-session-hardening F-001)** — Redis 서버 세션: 쿠키에는 세션 ID 만, 로그아웃·권한 회수 시 서버에서 즉시 폐기. 비밀번호 변경 경로는 아직 없다. 원 기록: 관리 세션은 서명 쿠키라 서버측 폐기 목록이 없다 — 로그아웃은 브라우저 쿠키를 비울 뿐이고, 복사된 쿠키 값은 만료(8시간)까지 서명상 유효하다. 강등·비활성화·삭제는 매 요청 DB 확인으로 즉시 끊긴다. 비밀번호 변경은 기존 관리 세션을 끊지 않는다(`authenticate` 는 비밀번호를 보지 않는다). | LOW | ADR-003. 서버 세션 저장소 없이 가는 선택. 비상시 `SESSION_SECRET_KEY` 교체로 모든 관리 세션을 끊을 수 있다. | 2026-10-12 | 관리 세션 탈취가 관측되거나 즉시 폐기가 규정 요구가 되면 Redis 세션 저장소(세션 id 쿠키 + 서버 데이터)로 바꾼다. |
| R-302 | **해소(2026-10-19, admin-session-hardening F-002)** — 로그인 이후 sqladmin 폼·삭제·로그아웃도 CSRF 토큰을 요구한다. 이전 상태: **부분 해소(2026-10-19, security-ops-hardening F-003)** — `/admin/login` POST 는 세션에 묶인 CSRF 토큰(synchronizer token, 레이트 리밋보다 먼저 상수 시간 비교)을 확인한다. 로그인 이후 sqladmin 폼·GET 로그아웃은 여전히 `SameSite=Strict`·`Path=/admin` 에 의존한다(security-ops-hardening R-601). 원 기록: sqladmin 폼에 CSRF 토큰이 없다 — `SameSite=Strict` + `Path=/admin` 에 의존한다. | LOW | ADR-003. sqladmin 0.32 가 폼 CSRF 를 제공하지 않는다. 모든 주요 브라우저가 Strict 를 지원한다. | 2026-10-12 | 같은 사이트의 다른 하위 도메인이 신뢰할 수 없는 콘텐츠를 서비스하게 되거나 Strict 미지원 클라이언트를 지원해야 하면 미들웨어 CSRF 토큰을 붙인다. |
| R-303 | 관리 세션 수명(8시간)은 코드 상수다. `SESSION_EXPIRE_SECONDS` 는 여전히 읽는 코드가 없다. | LOW | 명세가 8시간을 고정했다. 설정을 하나 더 늘리지 않았다. | 2026-10-12 | 운영이 수명 조정을 요구하면 `SESSION_EXPIRE_SECONDS` 를 관리 세션에 연결한다(설정 계약 테스트와 함께). |
| R-304 | 관리 로그인도 고정 창 rate limit 이다(창 경계 최대 2배 통과, 계정 잠금 없음). | LOW | service-hardening R-202 와 같은 결정(ADR-004). | 2026-10-12 | service-hardening R-202 의 재평가 조건과 같다. |
| R-305 | ~~기존 ModelView 5개의 `column_filters` 가 sqladmin 0.32 와 맞지 않아 목록 페이지가 500 이다(ledger F-006).~~ → **해소(2026-10-12, Round 3, ADR-011)** | — | 이번 요청 범위(로그인·설정·문서)가 아니다 — 뷰 정의 수정은 감독자 결정 대기. | 2026-10-12 | 감독자가 범위에 넣으면 각 뷰의 필터를 sqladmin 0.32 필터 클래스(`sqladmin.filters`)로 바꾸고 목록 페이지 스모크 테스트를 더한다. |
| R-306 | 로그인 화면의 Bootstrap CSS 는 CDN(jsDelivr)에서 받는다 — 오프라인·CDN 차단·엄격한 CSP 환경에서는 스타일 없이 표시된다(폼은 동작). | LOW | ADR-005. SRI 로 변조는 막는다. 정적 파일을 저장소에 두면 갱신 책임이 생긴다. | 2026-10-12 | 폐쇄망 배포가 생기면 CSS 를 저장소 정적 파일로 두고 `templates_dir` 옆에서 서비스한다. |
| R-307 | 예전 `ADMIN` 잔존 검사는 `ENV=test` 에서 돌지 않는다 — 로컬 `.env` 에 `ADMIN` 이 남아도 pytest 는 통과한다. | LOW | ADR-006. 다른 설정 검사(`validate_env_source` 등)와 같은 규칙. 개발 서버 기동(`ENV=development`)에서는 멈춘다. | 2026-10-12 | 테스트 환경에서도 잡아야 할 사고가 생기면 test 제외를 없앤다. |
| R-308 | 실제 Celery 워커 프로세스 기동은 여전히 검증하지 않는다 — CI 는 include 모듈 import·태스크 등록까지만 본다. | LOW | 명세 §4 는 import 오류를 CI 로 당기는 것까지다(orm-raw-repository R-005 부분 해소). | 2026-10-12 | 워커 기동 실패가 운영에서 관측되면 CI 에 `celery worker --pool solo` 단발 기동 스모크를 더한다. |
| R-309 | ~~`docs/guides/ARCHITECTURE.md` §12 의 revision 체인이 head 를 `e5a7c9d1f3b5` 로 적는다.~~ → **해소(2026-10-12, Round 3, ledger F-008)** | — | 이번 변경과 무관한 서술이다(사용자 지시: 범위 밖 정리 금지). | 2026-10-12 | 다음 문서 정리 요청 때 고친다. |
| R-310 | **해소(2026-10-19, security-ops-hardening F-004)** — core `LocalDateFilter`(`app/core/admin_filters.py`)가 `TIME_ZONE` 날짜를 UTC 범위로 바꿔 질의하고, `created_at` 이 있는 7개 뷰 모두에 붙었다. 원 기록: 관리 목록에서 `created_at` 으로 필터할 수 없다(정렬은 된다). | LOW | ADR-011. sqladmin 의 `OperationColumnFilter` 가 `UTCDateTime`(TypeDecorator)을 날짜로 보지 않아 500 이 나므로 뺐다. | 2026-10-12 | 기간 필터가 필요해지면 `UTCDateTime` 의 `impl` 을 보고 ISO 문자열을 aware datetime 으로 바꾸는 필터 클래스를 core 에 두고 각 뷰가 쓴다. |

<!--
규칙:
- 여기 있는 항목을 다음 라운드에서 새 finding 으로 다시 올리지 않는다.
- 재평가 조건이 참이 되면 ledger 로 승격한다(그때 비로소 "결함").
-->
