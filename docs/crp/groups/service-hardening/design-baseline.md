# Design Baseline — service-hardening (기준 설계 문서)

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
- 2026-10-12: 최초 선택 = 보통. 사유 — 2026-10-07 전체 검수 리뷰의 우선 조치 1~8 과 결정 질문
  (Redis 필수 여부·시각 정본·Celery 배치·로그인 방식)에 사용자가 한 번에 답했다. 남은 갈림길은
  단계 경계와 비가역 작업(스키마 변경·커밋 병합)뿐이다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

이 저장소는 "그대로 복사해 시작하는 FastAPI 출발점" 이다. 2026-10-07 전체 검수에서 출발점으로서
부족한 세 갈래가 드러났다 — ① 경계 보안(무인증 CRUD, 위조 가능한 접속 로그, refresh 회전·로그인
제한 없음), ② 모듈성 약속의 예외(Celery 태스크가 기능을 직접 import, 쓰지 않는 Redis 에 기동 의존),
③ SQLite 에서만 검증되는 데이터 의미(시각·정렬·잠금 읽기·DSN 인코딩). 이 그룹은 그 셋을 **단계
A → B → C → D → E → F1 → F2** 로 나눠 닫는다. 모든 단계는 단위 테스트를 동반하고, 같은 목적의
기능은 모듈 클래스 하나로 두며, 조합·데이터 전달·인증·자동 작업은 이 저장소의 주입 경로(provider
함수 → `Depends` → 생성자 주입, 등록 훅)를 따른다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "1,2,3,4,5,6,7,8 redis 필수, 9는 전통적인 방식과 fastapi에서 최신 사용하는 실무 코드를 기반으로, 일반적으로 개발되는 설계를 기반으로 작업 계획을 만들고 이를 기반으로 개발을 진행해줘. 각 단계는 단위 테스트가 반드시 진행되어야 한다. 모든 기능은 같은 목적의 기능이 하나의 모듈 클래스로 만들어져야 하고 필수 작업은 반드시 주입을 통해 조합, 데이터 전달, 인증 및 자동 작업 등이 진행되어야 하며…" | 공통: 단계마다 단위 테스트(가능하면 fail-on-revert), 같은 목적 = 모듈 클래스 하나, 협력 객체는 생성자 주입·조립은 provider. **A** CI 를 `uv sync --locked` 로, 게이트 파일 목록을 git 추적 목록으로 / DSN 을 `URL.create` 로(비밀번호 특수문자·IPv6·Alembic `%`) / ORM 잠금 읽기를 쓰기로 판정, 목록 기본 정렬 `created_at DESC, id DESC`. **B** 신뢰 프록시 홉 기반 클라이언트 IP, 접속 로그의 500 기록·민감 query 가림·컬럼 길이 절단, null PATCH 거부, DB 오류 코드별 변환, 리포트 기간 상한, 남은 리뷰 버그. **C** 엔드포인트 테스트 공용 override 헬퍼(read-only 표시 유지), MySQL ORM 스모크. **D** UTC·마이크로초 저장, 응답은 오프셋 포함 ISO 8601. **E** Redis 필수 유지 + `/ready` 에 Redis, Celery 태스크를 기능별로 두고 registry 로 발견. **F1** Argon2 해시(기존 bcrypt 점진 이전), JWT claims 강화, refresh 회전·재사용 탐지, 로그인·가입 rate limit. **F2** 인증 주체·소유권·슈퍼유저 2단계, 운영 도구 `create_superuser`. | Active | ADR-001~ADR-018 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | 단계 A·B·C·D·E·F1·F2 를 순서대로 진행하고 단계마다 독립 검증(ruff·mypy·전체 `pytest -m "not mysql"` skip 0·게이트)과 CRP 기록 뒤 커밋한다. 같은 목적의 기능은 모듈 클래스 하나로 두고, 협력 객체는 생성자 인자로 받으며 조립은 기능의 `dependencies` 모듈 provider 함수(`Depends`)가 한다. 구현이 하나뿐인 Protocol·팩토리는 만들지 않는다 — 테스트는 provider 를 `app.dependency_overrides` 로 바꾸거나 생성자에 가짜(fakeredis 등)를 넣는다. | 사용자 원칙("같은 목적 = 하나의 모듈 클래스", "필수 작업은 주입으로"). 단계를 섞으면 회귀 원인을 가를 수 없다(orm-raw-repository ADR-001 과 같은 이유). | Accepted | — |
| ADR-002 | 2026-10-12 | (A1) CI 의 의존성 설치는 모든 job 에서 `uv sync --locked` 로 한다. 게이트의 파일 목록은 `git ls-files -z` 로 만들고, git 을 쓸 수 없을 때만 작업 트리 순회로 대체한다. | `--frozen` 은 락이 최신인지 보지 않고 설치한다 — pyproject 에 추가한 의존성이 락에 없으면 조용히 빠진다. 주석("락이 어긋나면 실패")이 말하는 동작은 `--locked` 다. 작업 트리 순회는 무시 대상(로컬 `.env`·도구 캐시·로컬 전용 문서)까지 비밀 스캔·문서 경로 검사에 넣어, 로컬과 CI 의 판정이 갈라진다. | Accepted | — |
| ADR-003 | 2026-10-12 | (A2) DSN 은 `sqlalchemy.engine.URL.create(...)` 로 만들고 Settings 의 DB URL 속성은 `URL` 객체를 돌려준다(replica 포함). 로그용 표기는 `render_as_string(hide_password=True)`. Alembic 은 `ALEMBIC_DATABASE_URL` 이 있으면 `make_url`, 없으면 writer URL 의 드라이버만 `mysql+pymysql` 로 바꾸고, `migrations/env.py` 는 `%` 를 `%%` 로 넘긴다. Redis URL 의 비밀번호는 `quote(pw, safe="")` 로 인코딩한다. | f-string 조립은 비밀번호의 `@ / : # %` 에서 접속 정보 파싱을 깨고, `%` 는 Alembic 의 ConfigParser 보간에서 `ValueError` 를 낸다. 이 실패는 운영 비밀번호에서만 드러난다. | Accepted | — |
| ADR-004 | 2026-10-12 | (A3) `Select` 의 `_for_update_arg` 가 있으면 **쓰기**로 판정한다 — 라우터는 writer 로 보내고 read-only 세션은 거부한다. `BaseRepository.get_all` 은 기본 정렬 `created_at DESC, <PK> DESC`(모델에 `created_at` 이 없으면 PK 만)를 갖는다. 공개 메서드 수(INV-15 의 8개)는 늘리지 않는다. `created_at DESC` 단일 키 쿼리에는 PK 보조 키를 더한다. | text SQL 의 `FOR UPDATE` 는 막는데 ORM 잠금 읽기만 통과해, 라우터를 켠 구성에서 잠금이 replica 에 걸린다. 정렬 없는 offset 페이지네이션은 행이 중복·누락되고, 초 단위 시각에서는 `created_at` 동률이 흔하다. | Accepted | — |
| ADR-005 | 2026-10-12 | (B) 클라이언트 IP 는 core 모듈 클래스 `ClientIPResolver` 가 설정 `TRUSTED_PROXY_HOPS`(기본 0)로 판정한다 — 0 이면 직접 피어, N 이면 XFF 목록 + 직접 피어의 오른쪽에서 N번째, `ipaddress` 검증 실패 시 직접 피어. 접속 로그 미들웨어는 예외 시 500 으로 기록 후 다시 던지고, 민감 query 키 값을 `***` 로 가린다. 문자열 절단은 모델을 아는 home 기능이 컬럼 길이에서 도출해 한다. Update 스키마는 공통 기반 클래스가 nullable 이 아닌 필드의 명시적 null 을 422 로 거부한다. DB 무결성 오류는 한 곳에서 코드별(중복 409·NOT NULL 422·참조 대상 없음 422·참조 중 409·그 외 500)로 변환한다. 리포트 기간은 최대 366일·날짜 범위 상한을 둔다. | 왼쪽 XFF 채택은 클라이언트가 보낸 값이 그대로 남아 위조된다. 500 은 기록되지 않고, `?token=` 이 원문으로 쌓이며, 컬럼보다 긴 헤더는 strict 모드에서 그 요청의 기록을 통째로 잃는다. null PATCH 가 NOT NULL 위반을 409 "충돌"로 응답한다. | Accepted | — |
| ADR-006 | 2026-10-12 | (C) 엔드포인트 테스트의 세션 override 는 공용 헬퍼 하나를 거친다 — writer override 는 `using_writer`, read-only override 는 `mark_read_only` 를 적용한 세션을 yield 한다. 대표 ORM 기능은 `mysql` 마커 스모크로 CRUD·정렬 안정성·대소문자 중복·null PATCH·긴 접속 로그 필드를 MySQL 에서 확인한다. | 표시 없는 override 는 GET 핸들러의 몰래 쓰기를 통과시킨다 — 운영에서는 같은 요청이 `ReadOnlyRoutingError` 로 500 이다. ORM 기능 경로가 MySQL 에서 한 번도 돌지 않았다. | Accepted | — |
| ADR-007 | 2026-10-12 | (D) DB 시각은 **UTC·마이크로초**로 저장한다. core 모델의 `UTCDateTime` TypeDecorator(MySQL 은 `DATETIME(fsp=6)`)가 aware 값을 UTC 로 바꿔 저장하고 naive 값은 거부하며, 읽을 때 UTC tzinfo 를 붙인다. 기존 행은 Alembic 리비전에서 `CONVERT_TZ` 로 옮긴다(Asia/Seoul 은 DST 가 없다는 가정을 주석으로 남긴다). 응답은 오프셋 포함 ISO 8601, 리포트는 설정 `TIME_ZONE` 기준 영업일 집계를 유지한다. Celery 는 `enable_utc=True`. | `DateTime(timezone=True)` 가 MySQL 에서 오프셋과 소수 초를 잃는다 — 벽시계가 naive 로 돌아오고, `TIME_ZONE` 을 바꾸면 기존 행과 의미가 섞이며, 소수 초 반올림이 일별 집계를 바꾼다. 사용자 결정: 정본은 UTC. | Accepted | — |
| ADR-008 | 2026-10-12 | (E) **Redis 는 필수로 유지한다.** 클라이언트는 lifespan 이 소유하고, 주입 provider `get_redis` 하나(core)가 요청에 건넨다. `/ready` 는 DB 와 Redis 를 모두 확인하고(각 상한 2초) 하나라도 실패하면 503, 응답에 원문을 싣지 않는다. | 사용자 결정 "redis 필수". 단계 F1 의 refresh 저장소·rate limit 이 실제 소비처가 되어, "API 가 쓰지 않는 Redis 에 기동이 의존" 하는 비대칭이 사라진다. 필수라면 readiness 도 그 의존을 반영해야 한다. | Accepted | orm-raw-repository charter 2-4 의 "Redis readiness" 비목표 (ADR-018) |
| ADR-009 | 2026-10-12 | (E) Celery 태스크는 기능 패키지의 **선택 모듈 `tasks`** 로 둔다. 워커의 include 목록과 모델 등록은 `AppRegistry` 가 발견한 앱에서 만든다 — 중앙 파일이 기능을 import 하지 않는다. 태스크 본문의 서비스 조립은 그 기능의 provider 함수(세션을 인자로 받는 일반 함수)를 재사용한다. | "디렉터리가 곧 등록 선언" 이라는 약속이 Celery 에서만 깨져 있었다 — 기능 하나를 지우면 API 는 뜨지만 워커는 import 오류로 죽는다. registry 의 기존 선택 모듈 규칙(모듈 자체가 없으면 건너뛰고 모듈 안의 오류는 올린다)을 그대로 쓴다. | Accepted | — |
| ADR-010 | 2026-10-12 | (F1) 비밀번호 해시는 `pwdlib[argon2]`(Argon2)로 한다. 검증은 verify-and-update 의미 — 기존 bcrypt 해시(`$2` 접두사)는 기존 규칙으로 검증하고 성공하면 Argon2 새 해시를 돌려줘 로그인 때 다시 저장한다(점진 이전). 타이밍 균등화용 더미 해시도 Argon2. 의존성 추가: `pwdlib[argon2]`, dev `fakeredis`(`uv add` 로 락 갱신). | FastAPI 공식 문서가 현재 권하는 방식이고, 비밀번호 저장 권고(OWASP)의 1순위가 Argon2id 다. 기존 계정을 한 번에 재설정시킬 수 없으므로 로그인 시점 재해시가 유일한 무중단 이전 경로다. fakeredis 는 Redis 를 쓰는 실물 클래스를 그대로 시험하려고 둔다(가짜 인터페이스를 만들지 않는다 — ADR-001). | Accepted | — |
| ADR-011 | 2026-10-12 | (F1) JWT 는 core 의 `TokenService` 하나가 발급·검증한다. claims 는 `sub, type, iat, nbf, exp, jti, iss, aud`, access 는 `username`·`su`, refresh 는 `fam`(family id). 검증은 허용 알고리즘 목록·`audience`·`issuer`·필수 claim·`leeway` 를 모두 지정한다. 설정에 발급자·대상·leeway 를 더하고 알고리즘은 HS256/HS384/HS512 `Literal` 로 제한, access 기본 만료는 15분. | `jti` 가 없어 회전·폐기를 할 수 없었고, 알고리즘이 자유 문자열이었다. 검증을 core 에 두는 이유: 인증 주체 의존성(ADR-014)이 기능끼리 import 하지 않고 core 하나만 의존해야 한다. | Accepted | — |
| ADR-012 | 2026-10-12 | (F1) refresh 토큰은 **회전 + 재사용 탐지**를 Redis 로 한다(`RefreshTokenStore`, core). 발급 시 `jti → {fam, sub}` 를 만료와 같은 TTL 로 저장하고 사용자별 family 집합에 넣는다. 회전은 `GETDEL` 로 jti 를 소비하고, 없으면 재사용으로 보아 그 family 를 폐기하고 401. 폐기된 family 는 401. 사용자 비활성화·삭제 시 사용자의 모든 family 를 폐기한다. | 탈취된 refresh 토큰으로 만료(7일)까지 재발급을 계속 받을 수 있었다. 재사용 탐지(OAuth 2.0 Security BCP 의 refresh rotation)는 탈취자와 정상 사용자 중 늦게 온 쪽에서 family 전체를 끊는다. 원자성은 `GETDEL` 하나로 충분하다 — 경쟁 시 한쪽만 성공한다. access 토큰 즉시 폐기는 짧은 만료로 대신한다(비목표). | Accepted | — |
| ADR-013 | 2026-10-12 | (F1) 로그인·가입 제한은 Redis **고정 창** `RateLimiter`(core) 하나로 한다 — `INCR` + 첫 hit 에 `EXPIRE`, 초과 시 429 와 `Retry-After`. 제한은 핸들러 본문이 아니라 라우트 의존성으로 주입한다. 기준: 로그인 ip+username, 로그인 ip, 가입 ip. 로그인 성공 시 ip+username 카운터를 지운다. | 로그인 대량 호출(credential stuffing)이 해시 연산으로 스레드풀을 점유했다. 고정 창은 경계에서 최대 2배가 통과하는 한계가 있으나 구현·운영이 가장 단순하다 — 한계는 residual-risk 에 적는다. | Accepted | — |
| ADR-014 | 2026-10-12 | (F2) 인증 주체는 core 의 `Principal`(id, username, is_superuser)이고, 의존성 `get_current_principal` 이 Bearer access 토큰을 `TokenService` 로 검증해 **DB 조회 없이** 만든다. 성공 시 요청 상태에 user_id 를 남겨 접속 로그가 채운다. 사용자 엔티티가 필요한 곳(`/me` 등)만 DB 를 조회하는 `get_current_user` 를 쓴다. | 기능끼리 import 금지 규칙을 지키면서 모든 기능이 인증을 쓰려면 판정이 core 에 있어야 한다. 무상태 판정은 요청마다 DB 왕복을 없애고, 비활성화의 즉시성은 refresh 폐기 + 짧은 access 만료로 확보한다. | Accepted | — |
| ADR-015 | 2026-10-12 | (F2) 소유권은 core 의 `OwnershipPolicy` 한 클래스가 판정한다 — 소유자 또는 슈퍼유저만 수정·삭제, 아니면 403. 서비스 메서드가 주체를 인자로 받아 호출한다. blog·sns·reply 에 작성자 id 컬럼(nullable, index)을 Alembic 리비전으로 더하고, 기존 행(NULL)은 슈퍼유저만 수정한다. 작성자 표시는 서버가 주체에서 채운다. | 익명 사용자가 아무 글·계정을 수정·정지시킬 수 있었다(IDOR). 판정이 서비스마다 흩어지면 하나가 빠져도 보이지 않는다. | Accepted | — |
| ADR-016 | 2026-10-12 | (F2) 권한은 **슈퍼유저/일반 2단계**다(`users.is_superuser`, 기본 False). 관리 경로(catalog 쓰기·리포트·접속 로그 조회·사용자 목록·생성·삭제·활성/권한 변경)는 슈퍼유저 전용. 최초 슈퍼유저는 운영 도구 `create_superuser` 스크립트(Django `createsuperuser` 대응)가 만들거나 승격한다 — 서비스·리포지토리를 background 세션으로 조립해 주입 경로를 재사용한다. | 세분화된 RBAC 는 출발점의 비목표다. 두 단계만으로 리뷰가 지적한 노출(접속 로그·이메일 열거·계정 정지)을 모두 닫는다. | Accepted | — |
| ADR-017 | 2026-10-12 | SQLAdmin 정책은 **바꾸지 않는다** — 인증 백엔드를 붙이지 않고, 배포 환경의 `ADMIN=true` 는 `ADMIN_ALLOW_UNAUTHENTICATED` 확인이 있어야 기동한다(orm-raw-repository C-8 그대로). | 기존 결정(orm-raw-repository ADR-005·ADR-013)이 유효하다. 이 그룹의 API 인증과 Admin 인증은 별개 결정이며, Admin 인증은 비목표로 남긴다. | Accepted | — |
| ADR-018 | 2026-10-12 | 이번 요청(REQ-001)은 orm-raw-repository charter 2-4 의 비목표 "API Redis cache / Redis readiness / JWT lifecycle 확장" 과 그 residual-risk R-002("RBAC/권한 모델은 범위 밖") 중 **Redis readiness·JWT lifecycle·2단계 권한** 부분을 대체한다. 그 그룹 design-baseline 에 상태 주석과 이력 한 줄을 append 했다. runtime-lifecycle C-1·C-3, docs-learnability C-1·C-2 는 **그 그룹 작업의 범위 제약**이라 이 그룹의 변경(Base·예제 기능·라우트 인벤토리)을 막지 않는다 — 라우트 인벤토리 변경은 단계 F 에서 이유와 함께 테스트를 갱신한다. | 당시 비목표는 "그 그룹의 범위 밖" 이었고, 사용자가 이번에 명시적으로 범위에 넣었다. 조용히 넘기면 이전 기록과 현재 코드가 서로를 반박한다. API Redis cache 는 여전히 범위 밖이다. | Accepted | orm-raw-repository charter 2-4 (부분), orm-raw-repository residual-risk R-002 (부분) |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 필수 작업(서비스 조립·데이터 전달·인증·rate limit·자동 작업)은 **주입**으로 한다 — provider 함수 → `Depends` → 생성자. 핸들러 본문이 인증·제한을 직접 하지 않는다 — ADR-001·ADR-013·ADR-014.
- C-2: 계층 경계 — 기능끼리 import 금지(문서화된 auth → user 예외만), core → features 금지, utils → core 금지. 기능 간 공유가 필요하면 core 로 올린다 — ADR-014.
- C-3: commit 은 쓰기 핸들러가 응답 DTO 검증 후 정확히 1회. Repository·Dependency 는 commit 하지 않는다 — orm-raw-repository C-2 승계.
- C-4: Redis 는 필수다. API 기동과 `/ready` 모두 Redis 를 요구하며, Redis 실패를 조용히 무시하는 경로를 만들지 않는다 — ADR-008.
- C-5: DSN 은 문자열 보간으로 만들지 않는다. 로그·응답에 DSN 비밀번호·토큰·비밀번호·SQL 원문을 남기지 않는다 — ADR-003, orm-raw-repository C-5 승계.
- C-6: read-only 세션은 잠금 읽기를 포함한 모든 쓰기를 거부한다 — ADR-004.
- C-7: (단계 D 이후) DB 시각은 UTC 로 저장하고 naive 값 저장을 거부한다 — ADR-007.
- C-8: 토큰 검증은 core 의 `TokenService` 하나, 인증 주체 판정은 `get_current_principal` 하나를 거친다 — ADR-011·ADR-014.
- C-9: SQLAdmin 정책 불변(orm-raw-repository C-8) — ADR-017.
- C-10: 전체 suite 의 skip 0. 기존 테스트를 삭제하거나 느슨하게 만들어 통과시키지 않는다 — 동작이 바뀐 테스트는 새 계약으로 고치고 이유를 run-log 에 적는다.

## 5. 변경 이력
- v0.1 (2026-10-12): 최초 작성. REQ-001, ADR-001~018, C-1~C-10. orm-raw-repository design-baseline 에 ADR-018 상태 주석 append.
