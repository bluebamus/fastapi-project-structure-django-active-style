# Run Log — admin-login (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-10-12 (base SHA: `7a99987`) — 계획
- **트리거:** 사용자 요청 REQ-001(배포 전 확인 문서화, Bootstrap 로그인, create_superuser 로 `/admin` 로그인 테스트).
- **검수 범위:** `app/features/admin.py`·`main.py`·`config.py`, auth 기능 로그인 경로, core security(해시·rate limit·IP 판정), `scripts/create_superuser.py`, sqladmin 0.32 `Admin`·`AuthenticationBackend`·템플릿 로더, starlette `SessionMiddleware`.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **기준선:** main `7a99987`(service-hardening 종료: 1098 passed / 42 deselected / skip 0, alembic head `a7c3e9f1b2d4`).
- **이전 요구 충돌:** service-hardening ADR-017·C-9·R-203 과 orm-raw-repository ADR-005·C-8·ADR-013(SQLAdmin 무인증·확인 플래그) → 이 그룹 ADR-002·ADR-006 으로 대체, 각 문서에 상태 주석 append.
- **신규 finding:** CRIT 0 · HIGH 1 · MED 1 · LOW 2 (F-001·F-002·F-004·F-005)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-12 — REQ-001 구현
- **Fix:** F-001 · F-002 · F-004 · F-005 → **Fixed**
- **설계:** `verify_credentials` 를 auth 서비스 모듈로 추출하고 `AuthService.authenticate` 가 위임(동작 불변 — 기존 auth 테스트 그대로 통과). `AdminAuthBackend` 는 auth 기능에, 조립은 `create_admin_interface`. sqladmin 은 하위 앱이라 `request.app` 이 메인 앱이 아니어서 Redis 는 `app.state.redis` 를 조립부가 넘긴다. Bootstrap 5.3.8 CSS 를 jsDelivr·unpkg 에서 내려받아 두 파일이 같고 sha384 가 공개값과 같음을 확인.
- **동작이 바뀐 기존 테스트:** `tests/core/test_deployment_safety.py` — "배포 환경 ADMIN=true 는 확인 플래그 없이 거부" 와 "확인 플래그로 열면 WARNING" 두 계약이 없어져, "관리 화면을 켠 배포는 통과" 와 "예전 플래그가 남아도 기동·로그인 필요 로그" 로 고쳤다(`test_error_lists_every_problem_at_once` 는 ADMIN 기대를 뺐다). 기동 테스트는 로컬 `.env` 영향을 없애려 `.env` 없는 임시 작업 디렉터리에서 돌린다.

### Round 2 — 2026-10-12 — REQ-002 구현(ADMIN_DISABLED · 세션 범위 · 가이드 · 전 문서)
- **트리거:** 사용자 추가 요청 REQ-002 + 결정(`ADMIN` → `ADMIN_DISABLED`).
- **Fix:** F-003 · F-007 → **Fixed**. **신규:** F-006(MED, 범위 밖 — 감독자 결정 대기).
- **세션 범위 확인:** 감독자 가정과 코드가 일치했다 — 메인 앱 미들웨어는 CORS·`UserInfoMiddleware` 뿐이고 `SessionMiddleware` 는 sqladmin 하위 앱에만 있다. API 보호는 `get_current_principal`(Bearer)뿐. `SESSION_COOKIE_NAME` 은 접속 로그 기록용. `SESSION_SECRET_KEY` 소비처는 `app/features/admin.py`(관리 세션 서명)와 config 설정 검사(필수 환경 변수 목록·placeholder/길이)뿐.
- **동작이 바뀐 기존 테스트:** `tests/core/test_admin_lazy_import.py`·`tests/test_admin_wiring.py` 의 `ADMIN=false/true` 를 `ADMIN_DISABLED=true/false` 로(단언 동일).
- **가이드:** `docs/guides/workflows/admin-authentication.html` — 12절, Mermaid 도식 8개(구성도·주입 관계·기동 결정·로그인 시퀀스·요청별 인증·실패 경로·로그아웃·계정 수명주기), 기존 HTML 가이드와 같은 형식·Mermaid 11.12.0, `tests/test_docs_learnability.py` 의 `HTML_GUIDES` 에 등록.
- **낡은 서술 확인:** `git grep -n -E "인증 없|ADMIN=|ADMIN_ALLOW_UNAUTHENTICATED|ADMIN_UNAUTHENTICATED_ACK|unauthenticated|무인증"`(CRP 이력 제외). 남은 것은 모두 예외로 분류했다 — 이름 변경 안내(`.env.example`·config 메시지·README 문제 해결), 제거 회귀 테스트·이력 허용 목록(`scripts/review_gate.py`), Redis·MySQL 계정의 "인증 없는/무인증"(관리 화면과 무관), 고정 기준선 `docs/specs/**`(README 문서 유지 규칙상 고쳐 쓰지 않음).

### fail-on-revert (Round 1·2 공통)
대상 파일을 작업 폴더 밖에 복사해 두고 수정 전 내용(또는 결함을 되살린 내용)을 넣어 돌린 뒤 복사본으로 복원했다.

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| `app/features/admin.py` 를 main 판(인증 없음) | `tests/test_admin_login.py` | 4 failed · 16 errors · 5 passed |
| 로그인 템플릿을 sqladmin 기본 확장으로 | 화면 테스트 3 | 2 failed · 1 passed(이스케이프는 기본 템플릿도 통과) |
| `main.py`+`config.py` 를 main 판 | `test_admin_disabled.py`·`test_deployment_safety.py`·`test_admin_lazy_import.py` | 68 failed · 3 errors · 29 passed |
| `config.py` 만 main 판 | 제거 회귀 + `test_deployment_safety.py` | 67 failed · 28 passed |
| `home/tasks.py` 에 import 오류 주입 | `tests/core/test_celery_app.py` | 1 failed · 4 passed |
| 로그인 시 `session.clear()` 제거 | 세션 고정 테스트 | 1 failed |
| `authenticate` 의 활성·슈퍼유저 확인 제거 | 강등·비활성 테스트 2 | 2 failed |
| 로그인의 슈퍼유저 요구 제거 | 실패 4종·통합 흐름 | 2 failed · 3 passed(나머지는 비밀번호·사용자·활성으로 실패) |
| rate limit 판정 제거 | 429·카운터 초기화 | 1 failed · 1 passed |
| 쿠키 이름·path·samesite 기본값으로 | 쿠키 속성·`/admin` 밖 미설정 | 1 failed · 1 passed |

세션 범위 테스트 중 "API 가 관리 쿠키로 인증되지 않는다"·"`/admin` 밖에서 쿠키를 설정하지 않는다" 는 이번 변경 전에도 성립하던 성질의 **확인**이라 되돌릴 대상이 없다(대조군 `test_crafted_cookie_is_a_valid_admin_session` 이 그 쿠키가 실제로 유효함을 보인다).

### 실제 기동 스모크
- 저장소 밖 임시 폴더(`.env` 없음 — 설정은 환경 변수로만, 비밀 값은 실행마다 생성해 출력하지 않음)에서 uvicorn 을 127.0.0.1 빈 포트로 띄웠다. Redis 는 fakeredis `TcpFakeServer`(빈 포트), DB 는 SQLite 파일 — 런타임 DB 는 MySQL 전용이라 임시 폴더의 시작 스크립트가 `create_async_engine` 을 SQLite 로 바꿔 끼웠다(저장소 코드는 그대로). `ENV=development`, `DEBUG=true`(기동 DDL 로 테이블 생성).
- 결과: `/health` 200 · `/ready` 200 · `create_superuser --password-stdin` exit 0 · 익명 `GET /admin/` 302 → `/admin/login` · 로그인 화면 200(bootstrap@5.3.8) · 틀린 비밀번호 400 · 맞는 비밀번호 302(쿠키 jar 에 `admin_session`) · `GET /admin/` 200 · 관리 쿠키로 `GET /api/v1/auth/me` 401 · 로그아웃 302 · 로그아웃 뒤 `GET /admin/` 302. 기동 로그 "슈퍼유저 로그인 필요" 1줄.
- 발견: `GET /admin/user/list` 500(`column_filters` 의 sqladmin 0.32 비호환) → F-006 / R-305.

### 검사 수치 (최종)
- `pytest -m "not mysql"`: **1131 passed / 43 deselected / skip 0**(1098 → +33). `-m mysql --collect-only`: 43 수집(+1, `tests/integration/test_mysql_admin_login.py`). MySQL·브라우저 실행은 CI 몫(이 저장소에 `browser` 마커 없음).
- ruff check·format 클린. mypy(순수 Python 빌드 1.20.2, `--python-executable` .venv) 202 files 0 issues. bandit `-ll` 0.
- `scripts/review_gate.py`: structure·supply·docs·deps 통과(static 은 같은 도구를 위처럼 개별 실행 — 로컬 정책으로 컴파일된 mypy 가 막힌다). alembic heads `a7c3e9f1b2d4` 단일 — 리비전 추가 없음(`e5a7c9d1f3b5` 는 docstring 만).
- **수렴 판정:** `CONVERGED` — Open Fix 0(F-006 은 범위 밖, 감독자 결정 대기).
- **잔여 위험 변화:** R-301~R-309 등록. service-hardening R-203 해소, orm-raw-repository R-005 부분 해소.

### Round 3 — 2026-10-12 — REQ-003 (감독자 결정: 목록 필터·리비전 체인)
- **Fix:** F-006 · F-008 → **Fixed**. R-305·R-309 해소, R-310(날짜 필터 없음) 등록.
- **원인:** sqladmin 0.32 는 `column_filters` 항목에 `parameter_name` 을 가진 필터 객체를 기대한다. 모델 컬럼을 그대로 넣은 5개 뷰(blog·home·reply·sns·user)의 목록이 `AttributeError` 로 500 이었다. `OperationColumnFilter` 는 `UTCDateTime`(TypeDecorator)을 날짜로 보지 않아 `created_at` 에 문자열을 바인딩하므로 그 필터는 뺐다(ADR-011).
- **테스트:** `test_every_admin_list_page_and_filter_returns_200`(registry 가 등록하는 뷰 7개 전부, 필터가 있는 5개 뷰는 필터 14개 각각 쿼리 1건), `test_filter_queries_are_actually_exercised`(대조군, 필터 14개), `test_admin_detail_page_returns_200`. 테스트 앱이 registry 로 모든 뷰를 등록하도록 `build_admin_app` 을 고쳤다.
- **fail-on-revert:** 5개 `admin.py` 를 직전 커밋 판으로 되돌리면 6 failed(필터 있는 목록 5·대조군 1) · 3 passed(필터 없는 catalog·reports 목록, 상세 — 상세는 필터와 무관한 확인 테스트).
- **생성기:** `scripts/new_app.py` 템플릿은 `column_filters` 를 생성하지 않는다 — 예시 주석에 필터 클래스 사용법만 더했다.
- **기동 스모크(재실행):** 로그인 뒤 `/admin/{post,product,user-access-log,reply,sales-order,sns-post,user}/list` 7개 모두 200, 필터 쿼리 3건(`user?is_active=true`, `user-access-log?response_status=200&response_status_op=equals`, `post?author=a&author_op=contains`) 200, `/admin/user/details/<id>` 200, 앱 로그 ERROR 0.
- **검사 수치:** `pytest -m "not mysql"` 1140 passed / 43 deselected / skip 0(+9). ruff 클린, mypy 0 issues, 게이트 structure·supply·docs 통과.
- **수렴 판정:** `CONVERGED` — Open Fix 0.
