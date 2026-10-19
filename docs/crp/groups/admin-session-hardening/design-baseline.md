# Design Baseline — admin-session-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력:
- 2026-10-19: 최초 선택 = 보통. 사유 — 사용자가 세 항목과 Redis 방식(방법 2)·405 현행 유지를 정했고,
  감독자가 명세로 세부를 확정했다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

security-ops-hardening 이 남긴 관리 화면 잔여 위험을 닫는다. ① 로그인 이후 sqladmin 이 그리는 생성·수정·삭제
요청과 GET 로그아웃에 CSRF 토큰이 없다(R-601, admin-login R-302 의 남은 부분). ② 관리 세션은 서명 쿠키라
로그아웃해도 복사본이 8시간 유효하고 서버에서 폐기할 수 없다(R-602, admin-login R-301). ③ 날짜 필터는 하루
단위 연산만 있어 기간을 한 번에 지정할 수 없다(R-606).

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "관리 화면에 로그인한 뒤 쓰는 생성·수정·삭제 폼과, GET 방식 로그아웃 링크의 CSRF 토큰 / 관리 세션을 Redis로 옮기는 작업 / 필터 하나로 시작일~종료일 범위를 한 번에 지정하는 기능 — 이 작업들을 진행해줘. redis는 방법 2로 진행해줘. 405 문제는 현행 유지한다." (원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합·데이터 전달·인증·자동 작업은 주입, 모든 단계 단위 테스트·fail-on-revert) | ① 관리 세션을 Redis 서버 세션으로(방법 2 — 쿠키에는 세션 ID 만, 내용은 Redis, 즉시 폐기) ② 로그인 이후 모든 상태 변경 요청 CSRF + POST 로그아웃 ③ 날짜 필터 기간 연산 ④ 405 `Allow` 불완전은 **현행 유지**(결정 기록) ⑤ 문서·review | Active | ADR-001~ADR-006 |
| REQ-002 | 2026-10-19 | 감독자 후속 지시: "R-705 해소 — 관리 화면(UserAdmin)에서 사용자를 직접 수정(is_active=False·is_superuser 해제·비밀번호 변경)하거나 삭제하면 그 사용자의 관리 세션을 즉시 전부 폐기한다. after_model_change / after_model_delete 에서 기존 AdminSessionStore.revoke_user 를 부른다(중복 구현 금지). 변경 전후 비교로 … 일반 수정은 유지. 자기 강등 시 현재 세션도 끊김 — 문서화. Redis 오류는 fail-closed 와 일관되게." | 관리 화면 수정·삭제 훅에서 같은 폐기 함수 호출, 변경 전후 비교, 자기 강등 문서화, Redis 오류 503 | Active | ADR-007 |
| REQ-003 | 2026-10-19 | 감독자 후속 지시(세 저장소 동작 통일): "UserAdmin 폐기를 after_*(커밋 뒤)에서 on_model_change/on_model_delete(커밋 전)로 옮겨라. Redis 폐기가 실패하면 예외로 커밋 자체를 막아 'DB 는 비활성화됨 + 세션은 살아 있음' 상태를 남기지 않는다 … 같은 조건에서 API refresh 토큰도 기존 refresh 저장소의 revoke_user 로 폐기하라(UserService 와 같은 폐기 집합)." | 커밋 전 폐기, refresh 포함 같은 폐기 집합, 503 변환 장치 필요 여부 판단 | Active | ADR-008 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | **관리 세션은 Redis 서버 세션이다(방법 2).** `app/core/security/admin_session.py` 에 저장소 `AdminSessionStore`(저장·조회·TTL 갱신·삭제·사용자별 폐기)와 ASGI 미들웨어 `RedisSessionMiddleware` 두 클래스. 쿠키 `admin_session` 에는 `secrets.token_urlsafe(32)` 세션 ID 만(Path=/admin, SameSite=Strict, HttpOnly, staging/production Secure, Max-Age=절대 만료). Redis 키 `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}`, 값 JSON `{"data", "user_id", "created_at"}`, 사용자 인덱스 `admin:user_sessions:{user_id}`(SET, TTL=절대 만료, 세션 키를 담는다). 미들웨어는 `scope["session"]` 에 dict 를 넣어 `request.session` 인터페이스를 유지하고, 응답 시작 때 비었으면 삭제+쿠키 삭제, 새 세션·회전 요청이면 새 ID 발급+이전 키 삭제, 바뀌었으면 저장, 아니면 TTL 갱신. 쿠키의 ID 가 Redis 에 없으면 빈 세션 + 쿠키 삭제. `AdminAuthBackend` 는 부모 생성자(서명 쿠키 `SessionMiddleware`)를 부르지 않고 `middlewares=[RedisSessionMiddleware, AdminCsrfMiddleware]` 를 둔다. 저장소는 요청마다 `get_admin_session_store(app.state.redis)` 로 만든다(core provider — 사용자 서비스와 공유). `itsdangerous` 의존성은 다른 소비처가 없어 제거. | 저장소는 미들웨어·폐기 훅·테스트가 함께 쓰므로 미들웨어와 분리했다. 사용자 서비스가 쓰므로 core 에 둔다(기능→core 만 의존, sqladmin 미import). HMAC 키라 Redis 가 새도 쿠키를 만들 수 없고, `SESSION_SECRET_KEY` 교체가 전체 무효화 수단으로 남는다. 내용이 바뀐 때만 쓰므로 동시 요청(정적 파일 등)이 서로의 변경을 덮지 않는다. `request.session` 을 유지해 백엔드 login/authenticate/logout·sqladmin flash 가 그대로 동작한다. | Active | admin-login ADR-003(세션 쿠키 서명) |
| ADR-002 | 2026-10-19 | **만료 = 절대 + 미사용, 세션 고정 방지는 명시적 회전, Redis 장애는 503.** 설정 `ADMIN_SESSION_MAX_AGE_SECONDS=28800`·`ADMIN_SESSION_IDLE_SECONDS=1800`(`SessionSettings`, 둘 다 `ge=60`, 미사용 ≤ 절대 — `model_validator`). TTL = min(미사용, `created_at`+절대−now), 요청마다 다시 맞춘다. `load` 는 `created_at` 으로 절대 만료를 다시 확인해 TTL 이 남아도 거부한다. 로그인 성공 시 백엔드가 `rotate_session(request)`(scope 표시)를 부르고 미들웨어가 새 ID 발급·이전 키 삭제를 한다. 저장소 함수가 클라이언트 없음을 `RedisError` 로 올리고, 미들웨어는 `RedisError` 를 응답 시작 전이면 503 텍스트로 끝낸다(삼키고 통과시키지 않는다). | 절대 만료가 연장되지 않아야 탈취된 쿠키의 수명이 상한을 갖는다. scope 표시는 저장소를 백엔드에 또 주입하지 않고도 "이 응답에서 회전" 을 명확히 전한다. Redis 필수 정책(C-4, service-hardening)과 같은 fail-closed. 시계는 저장소에 주입해 테스트가 절대 만료를 시험한다. | Active | — |
| ADR-003 | 2026-10-19 | **즉시 폐기 훅은 refresh 폐기와 같은 지점이다.** `UserService` 가 생성자로 `admin_sessions: AdminSessionStore | None` 을 받고, `update_user`(비활성화·강등)·`delete_user` 가 `_revoke_sessions` 로 `RefreshTokenStore.revoke_user` 와 `AdminSessionStore.revoke_user` 를 함께 부른다. `get_user_service` 가 `Depends(get_admin_session_store)` 로 주입하고, `ADMIN_DISABLED=true` 면 provider 가 `None`(저장소 미생성). 비밀번호 변경 경로는 이 저장소에 없다(생기면 같은 훅). `authenticate` 의 매 요청 DB 확인은 유지(관리 화면에서 직접 편집한 강등 등 — 이중 방어). | 조합은 주입(원칙). 같은 사건(권한 회수)에 두 저장소를 같은 자리에서 끊어야 한쪽만 빠지는 일이 없다. | Active | — |
| ADR-004 | 2026-10-19 | **로그인 이후 CSRF = 하위 앱 미들웨어 `AdminCsrfMiddleware` 하나 + 템플릿 `base.html` 덮어쓰기 하나.** 대상: `/admin` 아래 POST·PUT·PATCH·DELETE 전부(`/login` 제외 — 백엔드 `login()` 이 같은 `csrf_valid` 로 한 번 검사). 토큰: 헤더 `X-CSRF-Token` 우선, 없고 본문이 폼(urlencoded·multipart)이면 **본문을 버퍼링해 폼에서 읽은 뒤 같은 바이트를 receive 재생으로 다운스트림에 넘긴다.** 실패는 403 텍스트(`CSRF_REJECTED_MESSAGE`). 클라이언트: `app/templates/admin/sqladmin/base.html` 이 `sqladmin_original/base.html` 을 상속해 `head_tail` 블록에만 `<meta name="csrf-token">`·로그아웃 URL meta·인라인 스크립트(같은 출처 POST 폼 submit capture 에 hidden `csrf_token`, `XMLHttpRequest.prototype.send`·`window.fetch` 에 헤더, 로그아웃 링크 클릭 → 토큰 실은 POST 폼)를 넣는다. 로그아웃: `_make_logout_post_only` 가 sqladmin `logout` 라우트를 같은 이름·엔드포인트의 POST 전용 라우트로 교체(GET 405). 로그인 성공 시 새 토큰(회전). | sqladmin 0.32 조사: 생성·수정은 네이티브 폼 POST(헤더를 실을 수 없다), 삭제·일괄 삭제는 jQuery `$.ajax` DELETE(본문 없음), 가져오기는 `fetch(FormData)`, 로그아웃은 GET 링크, 사용자 정의 action 은 GET. 폼은 hidden 필드밖에 길이 없어 헤더로 통일할 수 없다 — 버퍼링+재생은 Starlette 에서 다운스트림이 본문을 다시 읽는 안전한 방법이고, 큰 업로드(가져오기)는 스크립트가 헤더를 붙여 버퍼링하지 않는다. 403 을 텍스트로 둔 이유: 삭제 모달의 AJAX 오류 처리가 텍스트를 그대로 alert 하고, 오류 페이지(layout)는 익명 위조 요청에 메뉴를 보여 준다. `head_tail` 은 원본 어떤 화면도 덮어쓰지 않는 블록이다(`create.html` 은 `tail`, `edit.html` 은 `tail_js` 를 덮어쓴다). 라우트 교체는 sqladmin 코드를 복제하지 않고 이름을 유지해 `url_for` 가 그대로다. | Active | security-ops-hardening ADR-003 의 범위 확장(로그인 검사는 그대로) |
| ADR-005 | 2026-10-19 | **기간 필터는 기존 `LocalDateFilter` 의 연산 `range` 다.** 값 `YYYY-MM-DD~YYYY-MM-DD`(sqladmin 연산 필터는 값을 하나만 넘긴다), [시작일 지역 자정, 종료일 다음날 지역 자정) 을 UTC 로(양 끝 포함), 한쪽이 비면 열린 구간, 역순·형식 오류·둘 다 빈 값은 필터 미적용 + WARNING. 전용 템플릿 `sqladmin/filters/local_date_filter.html`(클래스 속성 `template` — sqladmin 이 필터 객체의 `template` 을 include 한다는 것을 확인)이 단일 날짜 폼(연산 3종, `type="date"`)과 기간 폼(날짜 입력 두 개 → 제출 직전 `~` 로 합침)을 그리고, 빠른 선택(오늘·최근 7일·최근 30일)은 `quick_ranges()` 가 만든 기간 링크다. | 같은 목적(created_at 지역 날짜 필터)은 한 클래스. 새 필터 클래스를 두면 7개 뷰·스캐폴드 주석을 다시 고쳐야 한다. 빠른 선택이 기간 연산으로 표현돼 security-ops-hardening R-606 이 함께 닫힌다. | Active | security-ops-hardening ADR-004 의 연산 확장 |
| ADR-007 | 2026-10-19 | **관리 화면(`UserAdmin`) 직접 수정·삭제도 즉시 폐기한다(REQ-002).** sqladmin 0.32 훅: `on_model_change`(폼 값 반영 전)가 `is_active`·`is_superuser`·`hashed_password` 를 `request.state` 에 기억하고, `after_model_change`(커밋 뒤)가 `loses_admin_access`(비활성화·슈퍼유저 해제·비밀번호 변경)일 때만, `after_model_delete` 는 항상 `revoke_user_sessions(request, id)` 를 부른다. 이 함수는 미들웨어가 scope 에 둔 저장소(`session_store_of`)의 기존 `revoke_user` 를 부르고, Redis 오류면 scope 에 실패 표시를 남긴 뒤 다시 올린다 — 미들웨어가 응답 시작 때 표시를 보고 503 으로 바꾼다. 기존 세션 저장은 `SET XX`(키가 있을 때만), 새 세션만 `create=True`. 자기 강등·비활성화는 지금 세션도 끊는다. | sqladmin 은 모델 훅의 예외를 삼켜 수정은 400 폼, 삭제는 목록 `error` 파라미터로 그린다 — 표시 없이 올리기만 하면 폐기 실패가 성공처럼 지나간다(fail-closed 와 어긋남). 폐기를 커밋 뒤에 두는 것은 롤백된 변경으로 세션을 끊지 않기 위해서다(대가: 503 이어도 변경은 저장됨, 매 요청 DB 확인이 이중 방어). `SET XX` 가 없으면 같은 요청에서 세션 내용이 바뀐 경우 응답 끝의 저장이 방금 지운 키를 되살린다. 저장소를 요청에서 꺼내는 이유: ModelView 는 registry 가 클래스로 등록해 생성자 주입이 없고, 같은 요청의 저장소(같은 Redis·설정)를 써야 한다. | **Superseded**(2026-10-19, ADR-008 — 폐기를 커밋 전으로, refresh 포함) | — |
| ADR-008 | 2026-10-19 | **관리 화면 폐기는 커밋 전에, API 와 같은 폐기 집합으로 한다(REQ-003).** `UserAdmin.on_model_change`(폼 값 반영 전)가 지금 값과 `data`(폼에 없는 필드는 지금 값)를 `loses_admin_access` 로 비교해 비활성화·슈퍼유저 해제·비밀번호 해시 변경일 때만, `on_model_delete` 는 항상 `revoke_user_access(refresh_store, admin_sessions, user_id)` 를 부른다. 이 함수는 `app/features/user/services/user_service.py` 에 하나로 두고 `UserService._revoke_sessions` 도 그것을 부른다(refresh family + 관리 세션). refresh 저장소는 세션 미들웨어 저장소의 Redis(`AdminSessionStore.redis`)로 `get_refresh_token_store(redis, get_token_service())` 가 만든다. Redis 오류는 훅 예외 → commit 건너뜀(롤백) → sqladmin 이 수정 400 폼·삭제 목록 `error` 로 표시. ADR-007 의 scope 실패 표시 → 503 변환 장치(`revoke_user_sessions`·`_REVOKE_FAILED`)는 **제거**했다. `SET XX`·변경 전후 비교는 유지. | sqladmin 0.32 `_queries.py` 확인: `_update_async` 는 `async with session_maker()` 안에서 `on_model_change` → 값 반영 → `commit`, `_delete_async` 는 `on_model_delete` → `delete` → `commit` 이라 on_* 예외는 commit 전에 전파된다(세션 컨텍스트 종료 = 롤백). 커밋 뒤 폐기는 Redis 오류 시 "DB 는 비활성화됨 + 세션은 살아 있음" 을 남겼다(503 이어도 상태가 어긋남). 커밋 전이면 실패가 변경 자체를 막으므로 sqladmin 이 오류를 삼켜 400·목록 오류로 그려도 성공처럼 지나가는 일이 없다 — 503 변환은 더 지킬 것이 없어 지웠다. 반대 방향(폐기 성공 후 커밋 실패)은 사용자가 다시 로그인하면 되는 안전한 쪽이다. API `UserService` 도 폐기 후 갱신·커밋 순서다. | Active | ADR-007 |
| ADR-006 | 2026-10-19 | **405 `Allow` 헤더 불완전(같은 경로를 메서드별 라우트로 나눈 경우 첫 라우트의 메서드만 실림)은 현행 유지한다** — 사용자 결정("405 문제는 현행 유지한다"). | 기능·보안 영향이 없고, 고치려면 FastAPI/Starlette 라우터 내부 구조(부분 일치 라우트 수집)에 의존해야 한다. | Active | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 쿠키에는 세션 ID 만, Redis 키는 HMAC 형태 — 세션 ID 원문·사용자 id 가 쿠키·키에 없다 — ADR-001.
- C-2: 로그아웃·강등·비활성화·삭제 뒤에는 그 사용자의 이전 쿠키 사본이 통하지 않는다 — ADR-001·ADR-003.
- C-3: 절대 만료는 연장되지 않고, 로그인은 세션 ID 를 회전한다 — ADR-002.
- C-4: Redis 를 쓸 수 없으면 관리 화면은 통과시키지 않는다(503) — ADR-002.
- C-5: `/admin` 의 POST·PUT·PATCH·DELETE 는 세션 토큰 없이는 처리되지 않는다. 로그아웃은 GET 으로 일어나지 않는다 — ADR-004.
- C-6: 메인 앱에는 세션 미들웨어가 없고, `ADMIN_DISABLED=true` 면 세션 미들웨어·CSRF 미들웨어·세션 저장소가 만들어지지 않는다(admin-login ADR-007·ADR-008 유지).
- C-7: 날짜 필터는 잘못된 입력에 500 을 내지 않는다(security-ops-hardening C-5 유지) — ADR-005.
- C-8: 스키마 변경 없음(alembic head 단일 그대로). 테스트는 실제 DB·Redis 에 접속하지 않는다(SQLite·fakeredis).

## 5. 변경 이력
- v0.3 (2026-10-19): REQ-003·ADR-008 append, ADR-007 Superseded(브랜치 `fix/admin-ui-revoke-precommit`).
- v0.2 (2026-10-19): REQ-002·ADR-007 append(R-705 해소, 브랜치 `fix/admin-ui-revoke`).
- v0.1 (2026-10-19): 최초 작성. REQ-001, ADR-001~ADR-006, C-1~C-8. 이전 그룹 security-ops-hardening R-601·R-602·R-606,
  admin-login R-301·R-302, log-redaction-fixes residual-risk(405) 에 상태 주석 append.
