# Design Baseline — admin-login (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-12 · 변경 이력:
- 2026-10-12: 최초 선택 = 보통. 사유 — 요청과 명세(감독자 작성)가 구현 방식·쿠키 속성·테스트 목록까지
  정했다. 남은 갈림길은 설정 이름 교체(사용자가 `ADMIN` → `ADMIN_DISABLED` 로 결정)뿐이었다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

service-hardening 이 API 에 인증·인가를 붙였지만 SQLAdmin(`/admin`)은 "인증 없음" 정책(orm-raw-repository
C-8, service-hardening ADR-017)을 유지해, 배포 환경에서는 확인 플래그로만 열 수 있었다. 이번 그룹은
`/admin` 에 **슈퍼유저 로그인**(Bootstrap 로그인 화면, 서명 세션 쿠키)을 붙이고, 관리 화면 자체를 완전히
끄는 설정(`ADMIN_DISABLED`)을 둔다. 함께 "배포 전에 해야 할 일"(프록시 홉 수·KST→UTC 리비전·첫 관리자·
관리 로그인)을 운영자가 보는 모든 문서·주석에 일관되게 적고, 세션 인증이 관리 화면에만 쓰인다는 사실을
확인해 테스트와 별도 가이드(`docs/guides/admin-auth-guide.html`)로 남긴다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "배포 전에 해야 할 일 에 대해 관련한 모든 문서와 주석에 업데이트를 수행해줘. bootstrap 기반으로 로그인 화면을 만들고 scripts/create_superuser.py로 생성자를 임의로 만들어 /admin에 로그인을 붙여 테스트를 수행해줘. 이후 로그인 페이지 구현 및 연동은 그대로 유지해줘." (이전 원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합·데이터 전달·인증은 주입, 모든 단계 단위 테스트) | ① 배포 전 확인 4항목(`TRUSTED_PROXY_HOPS`·KST→UTC 리비전·첫 관리자·`/admin` 로그인)을 README·`.env.example`·config·가이드·리비전·`ClientIPResolver`·스크립트·조립 지점 docstring 에 반영 ② `AdminAuthBackend` 하나로 로그인·인증·로그아웃(주입) ③ Bootstrap 로그인 화면 ④ create_superuser 로 만든 계정으로 통합·MySQL·기동 스모크 ⑤ 무인증 확인 플래그 제거 ⑥ Celery include import 테스트 | Active | ADR-001~ADR-005, ADR-009, ADR-010 |
| REQ-002 | 2026-10-12 | "이 작업과 관련하여 차후 설계 및 동작을 이해할 수 있게 별도의 admin 인증 가이드 문서를 만들어줘. 세션과 관련한 인증이 admin에만 적용되고 다른 api 인증 및 별도 작업에는 사용하지 않는것인지 확인하고 맞다면 이에 관련한 정보와 워크플로우 흐름도 등 상세한 설명을 정리해줘. 필요한 모든 도식화를 구현해 설명에 추가해줘. admin 페이지 자체를 사용하지 않는 설정이 존재해야 한다. 이 설정이 true이면, admin 페이지에 대한 링크 자체가 존재하지 않아야 한다. 이는 보안을 위해서 존재해야 한다." + "관련하여 모든 문서도 내용을 업데이트 하여 반영해줘." 사용자 결정: 기존 `ADMIN`(false=끔)을 `ADMIN_DISABLED`(true=끔)로 교체 | ① `ADMIN` 제거·`ADMIN_DISABLED` 신설, 잔존 시 기동 거부 ② true 면 마운트·응답·로그·미들웨어 어디에도 관리 흔적 없음 ③ 세션 범위(관리 전용) 확인과 테스트 ④ HTML 가이드(도식 포함) ⑤ 모든 문서·생성 템플릿 반영 | Active | ADR-006~ADR-008, ADR-010 |
| REQ-003 | 2026-10-12 | 감독자 결정: "F-006/R-305 를 고친다 — 로그인이 붙은 관리 화면의 목록 페이지가 500 이면 사용자 요청(\"/admin 로그인 테스트\")이 성립하지 않는다." + "R-309: ARCHITECTURE §12 리비전 체인 head 를 실제 head 로 고친다." | ① 모든 ModelView 의 `column_filters` 를 sqladmin 0.32 필터 클래스로 ② 모든 목록(필터 쿼리 포함)·상세 1건 200 테스트 ③ 생성기 템플릿 안내 ④ 리비전 체인 문서 | Active | ADR-011 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | `feat/admin-login` 브랜치(main `7a99987` 기준)에서 진행한다. 변경마다 단위 테스트와 fail-on-revert 를 확인하고, 검사(ruff·mypy·`pytest -m "not mysql"` skip 0·게이트 static 외 그룹)를 통과시킨 뒤 커밋한다. 병합·푸시는 감독자가 한다. | 사용자 규칙(피처 브랜치·PR 없음). | Active | — |
| ADR-002 | 2026-10-12 | `/admin` 인증은 `sqladmin.authentication.AuthenticationBackend` 를 상속한 **`AdminAuthBackend` 한 클래스**(`app/features/auth/admin_auth.py`)가 맡는다. 협력 객체는 생성자로 받는다 — 세션 팩토리(운영 `background_db_session`), core `PasswordHasher`, `RateLimiter` 를 돌려주는 함수, `ClientIPResolver`, 서명 키, `https_only`. 자격 확인은 API 로그인과 **같은 함수** `verify_credentials`(auth 서비스 모듈, `AuthService.authenticate` 가 위임 — Argon2·bcrypt 재해시·비활성 거부·더미 해시)를 쓰고, 그 위에서 `is_superuser` 를 요구한다. `authenticate` 는 **매 요청** 세션의 사용자 id 로 DB 를 다시 봐서 활성·슈퍼유저가 아니면 세션을 비우고 거부한다. 조립은 기존 조립 지점 `app/features/admin.py` 의 `create_admin_interface()` 가 `Admin(..., authentication_backend=..., templates_dir=...)` 로 한다(테스트는 백엔드를 인자로 바꿔 넣는다). 의존성 `itsdangerous` 추가 — starlette `SessionMiddleware` 가 쿠키 서명에 쓰며 지금까지 설치돼 있지 않았다. | 위치: core 는 features 를 import 할 수 없고(service-hardening C-2), auth → user 의존은 문서화된 예외라 auth 기능에 둔다. 기능의 `admin.py` 이름은 registry 의 `admin_views` 계약이라 피했다. 로그인 규칙을 두 벌 두면 비밀번호 이전·열거 방지가 갈라진다. 매 요청 DB 확인은 강등·비활성화를 즉시 반영한다(API 의 무상태 판정과 다른 선택 — 관리 화면은 요청 수가 적고 권한이 크다). | Active | service-hardening ADR-017, orm-raw-repository ADR-005(C-8) |
| ADR-003 | 2026-10-12 | 관리 세션은 `/admin` 하위 앱에만 붙는 starlette `SessionMiddleware` 의 서명 쿠키다 — 이름 `admin_session`(접속 로그가 읽는 `SESSION_COOKIE_NAME` 과 다름), `Path=/admin`, `SameSite=Strict`, HttpOnly, `Max-Age` 8시간, `Secure` 는 ENV 가 staging/production 일 때. 서명 키는 기존 `SESSION_SECRET_KEY`. 로그인 성공 시 `session.clear()` 뒤 사용자 id 만 저장(세션 고정 방지). 로그아웃은 `session.clear()`. | 명세. 서버 저장소 없는 서명 쿠키라 Redis·DB 에 세션 테이블이 필요 없다. 남는 위험(서버측 폐기 없음·CSRF 토큰 없음)은 residual-risk R-301·R-302. | Active | — |
| ADR-004 | 2026-10-12 | 로그인 시도는 기존 `RateLimiter`(Redis 고정 창)로 IP 기준·IP+사용자명 기준 두 번 센다. 키 접두사는 `admin:rl:` 로 API(`auth:rl:`)와 나누고, 한도는 API 와 같은 `AUTH_LOGIN_MAX_ATTEMPTS`·`AUTH_LOGIN_IP_MAX_ATTEMPTS`·`AUTH_LOGIN_WINDOW_SECONDS` 를 쓴다. 초과는 로그인 화면을 429 + `Retry-After` 로 다시 그리고, 성공하면 IP+사용자명 카운터를 지운다. Redis 클라이언트는 lifespan 이 `app.state.redis` 에 두므로 조립부가 `lambda: RateLimiter(app.state.redis)` 를 넘긴다. 실패·성공·초과를 로그로 남기되 비밀번호·해시는 싣지 않고 사용자명은 64자로 자른다. | sqladmin 은 하위 앱으로 마운트돼 `request.app` 이 메인 앱이 아니라서 `get_redis(request)` 를 쓸 수 없다. API 와 키를 섞으면 한쪽 실패가 다른 쪽을 막는다. | Active | — |
| ADR-005 | 2026-10-12 | 로그인 화면은 `app/templates/admin/sqladmin/login.html` 이 sqladmin 기본 템플릿을 덮어쓴다(`templates_dir` 의 `FileSystemLoader` 가 `ChoiceLoader` 첫 번째 — sqladmin 0.32 `Admin.init_templating_engine` 실측). base 를 확장하지 않는 독립 HTML(`lang="ko"`, viewport), **Bootstrap 5.3.8** CSS 를 jsDelivr 에서 `integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"` + `crossorigin="anonymous"` 로 불러온다(jsDelivr·unpkg 실제 파일이 같고 계산한 해시가 getbootstrap.com 공개값과 같음). JS 없음. 실패 메시지는 백엔드가 `InvalidCredentialsException.message`(한국어, API 와 같은 문구)로 직접 그린다(400). 사용자 요청 "로그인 페이지 구현 및 연동은 그대로 유지" 에 따라 이 화면과 연동은 이후 작업에서도 유지 대상이다(C-6). | sqladmin 기본 로그인은 base 템플릿(Tabler)을 확장하고 영어 메시지를 쓴다. 템플릿 위치 관례가 저장소에 없어 명세의 기본 위치를 쓴다. | Active | — |
| ADR-006 | 2026-10-12 | 설정 `ADMIN`(true=켬)을 **`ADMIN_DISABLED: bool = False`(true=끔)로 교체**한다. `.env`·환경 변수에 `ADMIN` 이 남아 있으면 `config.validate_renamed_settings()` 가 기동을 멈춘다(test 제외 — 다른 설정 검사와 같다, 대소문자 무시, 값은 메시지에 싣지 않음). 감지는 config 안에서만 한다. 예전 확인 플래그 `ADMIN_ALLOW_UNAUTHENTICATED` 와 배포 게이트의 "배포 환경 ADMIN=true 거부" 규칙·기동 WARNING 은 없앤다(남은 키는 `extra="ignore"` 로 무시 — 기동 회귀 테스트). 게이트 docs 검사는 이 두 이름을 CRP 이력 인용으로 허용한다(`DOC_ALLOWED_MISSING_ENV`). | 사용자 결정. 의미가 반대인 이름 변경이라 조용히 무시하면 `ADMIN=false`(끄려던 배포)가 관리 화면을 **켠다** — 그래서 무시하지 않는다. 인증이 붙어 무인증 확인 플래그는 의미가 없다. | Active | orm-raw-repository ADR-013 의 ADMIN 확인 플래그 부분 |
| ADR-007 | 2026-10-12 | `ADMIN_DISABLED=true` 면: ① `/admin`·`/admin/`·`/admin/login`·`/admin/statics/...` 모두 404(마운트 없음, sqladmin 미import 가드 유지) ② 앱이 내보내는 어떤 응답(OpenAPI·DEBUG `/docs`·오류 본문·헤더)에도 `/admin` 이 없음 ③ 기동 로그는 "관리 화면 비활성화 (ADMIN_DISABLED=true)" 만 — 경로 없음 ④ 관리 세션 미들웨어·인증 백엔드를 만들지 않음. 각각 `tests/test_admin_disabled.py` 가 깨끗한 서브프로세스에서 고정한다. | 사용자 요구 "링크 자체가 존재하지 않아야 한다(보안)". 저장소 문서의 링크는 앱 응답이 아니므로 별개다. | Active | — |
| ADR-008 | 2026-10-12 | **세션 인증은 `/admin` 전용이다(확인 결과).** API 인증은 Bearer JWT(`get_current_principal`)뿐이고 메인 앱에 `SessionMiddleware` 가 없다. `SESSION_COOKIE_NAME` 은 접속 로그 미들웨어가 session_id 를 기록용으로 읽을 뿐이다. `SESSION_SECRET_KEY` 소비처는 관리 세션 서명(`app/features/admin.py`)과 config 의 설정 검사뿐이다. 고정 테스트: 메인 앱 미들웨어에 세션 없음·하위 앱에만 있음, 유효한 `admin_session` 쿠키로 API 보호 경로 401, `/admin` 밖 응답은 그 쿠키를 설정하지 않음. API 에 세션 인증을 섞지 않는다(C-3). | 감독자 사전 확인과 코드가 일치했다. 쿠키 인증을 API 에 섞으면 CSRF 방어가 필요해지고 토큰 폐기 모델이 둘로 갈라진다. | Active | — |
| ADR-009 | 2026-10-12 | Celery include 모듈을 실제로 import 해 각 모듈이 태스크를 등록하는지 보는 테스트를 둔다(`celery_app.loader.import_default_modules()` — 워커 기동과 같은 경로). | `tasks.py` 의 import 오류가 워커 기동 때가 아니라 CI 에서 드러나게(명세 §4). | Active | — |
| ADR-010 | 2026-10-12 | "배포 전 확인" 은 README 운영 배포 체크리스트가 소유하고(항목 2a 첫 관리자·2b 관리 화면/`ADMIN_DISABLED`/`SESSION_SECRET_KEY`·4 `TRUSTED_PROXY_HOPS`·7 KST→UTC 백업·`_LOCAL_OFFSET`), `.env.example`·config Field 주석·`ClientIPResolver`·리비전 docstring(맨 위 경고)·스크립트·조립 지점 docstring 은 같은 내용을 그 자리의 맥락으로 적는다. 관리 인증의 설계·흐름·위협 모델은 새 HTML 가이드 `docs/guides/admin-auth-guide.html` 이 소유하고 README 문서 표·ARCHITECTURE §10.3 이 링크한다. | 한 주제는 한 문서가 소유한다(README 문서 유지 규칙). | Active | — |
| ADR-011 | 2026-10-12 | ModelView 필터는 sqladmin 0.32 의 `sqladmin.filters` 클래스로 준다 — bool 은 `BooleanFilter`, 문자열·숫자는 `OperationColumnFilter`. `created_at`(`UTCDateTime`) 필터는 뺀다 — `OperationColumnFilter` 는 `TypeDecorator` 를 날짜 타입으로 보지 않아 문자열을 그대로 바인딩하고, `UTCDateTime` 이 naive·문자열을 거부해 500 이 난다. 목록은 `created_at` 정렬로 본다. 생성기 템플릿(`scripts/new_app.py`)은 필터를 만들지 않으므로 예시 주석만 더했다. | 감독자 결정(REQ-003). 날짜 필터를 살리려면 `UTCDateTime` 용 필터 클래스를 새로 써야 해 범위를 넘는다(R-310). | Active | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 인증·조합·데이터 전달은 주입이다 — `AdminAuthBackend` 는 협력 객체를 생성자로 받고, 조립은 `app/features/admin.py` 한 곳이 한다 — ADR-002.
- C-2: 계층 경계 유지 — core → features 금지, 기능 간 import 는 문서화된 auth → user 만. 관리 인증 모듈은 `ADMIN_DISABLED=false` 일 때만 import 된다 — ADR-002·ADR-007.
- C-3: 세션(쿠키) 인증은 `/admin` 전용이다. API 인증은 Bearer JWT 하나 — ADR-008.
- C-4: 로그인 실패 사유를 구분하지 않고, 비밀번호·해시를 로그·응답에 남기지 않는다 — ADR-002·ADR-004.
- C-5: `ADMIN_DISABLED=true` 면 관리 화면의 흔적(경로·링크·로그·미들웨어)이 앱 어디에도 없다 — ADR-007.
- C-6: Bootstrap 로그인 화면과 그 연동(`templates_dir`·`AdminAuthBackend`·create_superuser 계정)은 유지한다 — 사용자 지시, ADR-005.
- C-7: 전체 suite skip 0, 기존 테스트를 느슨하게 만들어 통과시키지 않는다. 동작이 바뀐 테스트는 새 계약으로 고치고 run-log 에 이유를 적는다(service-hardening C-10 승계).

## 5. 변경 이력
- v0.1 (2026-10-12): 최초 작성. REQ-001·REQ-002, ADR-001~ADR-010, C-1~C-7. service-hardening ADR-017·C-9·R-203 과 orm-raw-repository C-8 에 상태 주석 append.
- v0.2 (2026-10-12): REQ-003 · ADR-011 — 관리 목록 필터 호환·문서 리비전 체인.
