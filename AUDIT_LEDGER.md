# AUDIT_LEDGER.md — 감사 작업 원장 (append-only)

> 이 원장은 감사 실행 전반에 걸쳐 append-only로 유지된다. 코드를 바꾸는 모든 작업 단위마다
> 변경 전/후 상태, 설계 결정과 이유, 검증 결과, 이전 작업과의 관계(신규/보완/대체/회귀 위험)를 기록한다.
> 회귀 방지 비교 검수 표(5.6.2)도 여기에 누적한다.

---

## 실행 #1 — 2026-07-08

- **브랜치**: `audit/full-review-2026-07-08` (from `main` @ 21f7a64)
- **패키지 매니저**: uv (uv.lock 존재)
- **대상**: 전체 코드베이스 (Django 스타일 자동 앱 발견 FastAPI, 도메인 계층형)
- **원장 상태**: 신규 생성 (과거 실행 없음)

### 0단계 — 안전 준비

| 항목 | 결과 |
|---|---|
| 작업 트리 | clean |
| 브랜치 | audit/full-review-2026-07-08 생성 |
| 패키지 매니저 | uv |
| 베이스라인 테스트 | **67 passed, 0 failed** (uv 가 Python 3.14.4 사용) |

### 1단계 — 정적 분석

설치 도구: `bandit`(uvx 임시 실행, 미영구화). ruff/mypy 는 dev 의존성에 이미 존재.

**작업 1-A · `0220eba` style(ruff): apply ruff formatter**
- 변경 전: `ruff format --check` 57개 파일 재포맷 대상(모듈 docstring 뒤 빈 줄, 다중행 함수 호출 등). `ruff check` 는 통과.
- 결정: 순수 스타일·동작 보존. 이후 의미적 diff 오염 방지 위해 최우선 독립 커밋.
- 변경 후: `ruff format` clean, `ruff check` clean. tests 67 passed.
- 관계: 신규.

**작업 1-B · `8bc17be` fix(types): mypy 해결(동작 보존)**
- 변경 전: `mypy app config.py main.py scripts` = **49 errors / 12 files**.
- 식별 문제 및 조치:
  - `filters.py:42` FrameType|None 역참조 표현 부정확 → 명시 주석.
  - `pagination` T→BaseModel(model_fields), ModelT→Base(model.id).
  - `models_base.Base` 에 매핑되지 않는 `id: Mapped[Any]` 선언 추가 — 모든 도메인 모델이 `id: Mapped[str]` 를 직접 선언하는 실제 불변식을 제네릭 Repository 계약에 반영. **런타임/스키마 무영향**을 전체 테스트(DB/ORM/endpoint/alembic 포함)로 검증.
  - `repository_base` DML 결과 `CursorResult` cast → rowcount/no-any-return 6+5건.
  - `user_info_middleware` __init__ ASGIApp, dispatch RequestResponseEndpoint.
  - `run_async` 제네릭(_T) → celery task 반환 타입 정합.
  - routers ×5 `responses` 상수 `dict[int|str, dict[str,Any]]` 주석.
  - mypy override 에 `celery.*` 추가.
- 변경 후: **49→4 errors**. 남은 4 = SQLAdmin formatter 스텁 부정확 3(`admin.py` home) + 중첩 `selectinload(str)` 잠재버그 1(`repository_base.py:123`, 3단계에서 다룸).
- 검증: ruff/format clean, mypy 4(문서화된 잔여), tests 67 passed.
- 관계: 신규. 회귀 없음.

**작업 1-C · `cb384b2` fix(security): B104 host 이전**
- 변경 전: `main.py` `host="0.0.0.0"`(bandit B104 Medium, 모든 인터페이스 바인드).
- 결정: 안전 기본값(127.0.0.1)으로 설정 이전, 컨테이너는 env HOST=0.0.0.0. **동작 변경(보안 하드닝)** — 명시.
- 변경 후: bandit(비테스트) medium+ **0건**. `.env.example` 에 HOST/PORT 키 추가.
- 검증: ruff/mypy/tests 67 passed.
- 관계: 신규. **Human decision**: 배포 시 HOST=0.0.0.0 주입 필요.

**bandit 요약**: 비테스트 실제 이슈는 B104 1건뿐(수정 완료). 나머지 68 Low 는 전부 테스트 파일의 `assert`(B101) = 오탐. 프로덕션 코드에 assert 없음.

### 2단계 — FastAPI 특화 점검 (코드 변경 없음, 관찰만)

| 점검 항목 | 결과 |
|---|---|
| async 라우트 블로킹 호출 | **없음**. 앱 코드 전역에 sync IO(requests/open/time.sleep/subprocess 등) 부재. DB 는 전부 async(aiomysql/AsyncSession). |
| response_model | **완전**. 각 도메인 라우터 5개 중 4개 + DELETE(204 No Content)는 response_model 불필요. home 5/5. |
| Pydantic 검증 공백 | 없음. `RequestValidationError` 전역 핸들러가 422 로 변환(500 누수 아님). |
| CORS 오설정 | **안전**. 기본값 `allow_origins=["*"]` + `credentials=False`(위험 조합 아님), 경고 주석도 존재. |
| Depends/세션 수명 | **양호**. 요청 스코프 `get_session`(async_sessionmaker, expire_on_commit=False), 트랜잭션 경계는 기능 의존성이 yield 후 commit, 예외 시 teardown 롤백. 백그라운드는 분리 풀. |
| ORM N+1 | 해당 없음. 모델에 `relationship()` 정의가 전혀 없어 지연로딩 경로 자체가 부재. 서비스 쿼리는 단순 count+select. |
| 예외 처리 | 조용한 삼킴 없음. `except Exception` 5곳은 모두 (a)롤백 후 재발생 또는 (b)미들웨어 fire-and-forget 로그저장 실패의 의도적 격리(exc_info 기록). |

### 3단계 — 로직·구조 리뷰 (코드 변경 없음)

- **F-1 (잠재버그, 도달불가)**: `repository_base.py:123` 중첩 eager-loading `load_option.selectinload(part)` 에 문자열 전달. SQLAlchemy 2.0 체인 로더는 `QueryableAttribute` 를 요구하므로 `relations=["a.b"]` 사용 시 런타임 실패. **단 앱 내 호출자 0, 모델에 relationship 0** → 현재 도달 불가. 재사용 스캐폴딩이므로 소비자가 관계를 정의해 쓰면 발현. mypy 도 이 지점을 arg-type 오류로 지목(잔여 4건 중 1). → **자동수정 보류**(검증 불가·동작 변경), 권고안 첨부.
- **관찰**: `BaseRepository`(1005줄)의 실제 사용 메서드는 `create/get_by_id/get_one/get_all/count/update/delete` 7종뿐. 나머지(eager-loading/bulk/upsert/partial/join/batch)는 미사용. 단 **구조 템플릿**의 재사용 베이스이므로 죽은코드 제거 대상 아님 — 표면적/문서 정합성 관점으로만 보고.
- **관찰**: `UUIDMixin`/`TimestampMixin`(models_base) 정의돼 있으나 도메인 모델은 상속하지 않고 `id`/`created_at` 을 각자 인라인 선언 → 미사용 믹스인(경미한 불일치).

### 5단계 — 설계·의도 정합성 (코드 변경 없음)

**5.1 파악한 의도(README/코드 교차)**: `app/domains/*` 자동발견 FastAPI 구조 템플릿. 3계층(Router→Service→Repository→DB), UnitOfWork 미사용·의존성 트랜잭션 경계, MySQL(async)+Redis+Celery+SQLAdmin+Scalar. 실행은 `uv sync` → `uv run uvicorn main:app`.

**5.2 정합성 대조**:
| 항목 | 대조 결과 |
|---|---|
| 자동 앱 발견 | ✅ 구현·동작(registry.discover, `/api` 마운트) |
| 3계층 경계 | ✅ 라우터는 DB/비즈니스 로직 없이 서비스만 호출, 서비스가 repository 사용 |
| 트랜잭션 경계(UoW 미사용) | ✅ `get_<name>_service` yield 후 commit, 예외 시 get_session 롤백 |
| 엔드포인트 문서 | ✅ README 표 ↔ 실제 라우터 경로 일치(home 5종 검증, CRUD 4도메인 동일 패턴) |
| 실행/환경변수 | ✅ 커맨드·env 키 일치. README uvicorn CLI 실행은 `--host 0.0.0.0` 명시(=main.py __main__ 우회, B104 수정과 무충돌) |
| **N+1 Eager Loading "내장"** | ⚠️ **드리프트**: 특징/Repository 계층에 "N+1 문제 해결"로 광고되나 모델에 relationship 0·호출자 0·중첩경로 결함(F-1). API 로는 존재하나 미검증 기능. |

**5.3 설계 평가**: 관심사 분리·응집도 양호, 순환 의존 없음, 설정/시크릿은 Pydantic Settings+env 로 일관, 예외/로깅 일관, async 일관. **경미 관찰**: 미들웨어 등록 순서상 CORS 가 user_info 보다 내측(먼저 add) → 관례상 CORS 최외곽 권장(에러 응답 CORS 헤더 보장). → 보고서 권고.

---

## 5.6.2 회귀 방지 비교 검수 표

과거 실행 없음(원장 신규). 본 실행 내부의 이전 작업 대비 회귀 여부:

| 항목 | 이전 작업의 상태·문제 인식 | 현재 방향의 상태·문제 인식 | 회귀 | 판단·근거 |
|---|---|---|---|---|
| ruff format(1-A) | 미포맷 57파일 | 포맷 적용, 최우선 커밋 | 없음 | 동작 보존, 이후 의미 diff 격리 |
| Base.id 타입선언(1-B) | 제네릭 `.id` mypy 오류 | 매핑 안 되는 선언으로 불변식 반영 | 없음 | 전체 테스트(DB/alembic 포함)로 런타임 무영향 검증 |
| B104 host(1-C) | host 하드코딩 0.0.0.0 | 127.0.0.1 안전기본+env | 없음(개선) | 동작변경이나 보안 하드닝, README uvicorn 실행과 무충돌 |
| F-1 미수정 결정(3) | (신규 식별) | 자동수정 보류·문서화 | 없음 | 도달불가·검증불가, 소비자용 권고안 제공 |
| F-1 재개 수정(후속) | 보류(도달불가·검증불가) | 수정+회귀테스트로 검증 후 적용 | 없음 | 소유자 "진행" 지시로 재개. 격리 모델 테스트로 검증 확보 → 보류 근거(검증불가) 해소 |

---

## 실행 #1 (후속) — 2026-07-08 · 보류항목 처리

소유자 "진행" 지시에 따라 보고서 §4 보류 4건 중 **코드로 안전·검증 가능한 2건**을 처리. 배포 HOST 주입(1)·템플릿 방향(3)은 소유자 결정 영역이라 코드 변경 없음(보류 유지).

**작업 F-1 · `9f11513` fix(orm): 중첩 eager-loading 정상화**
- 변경 전: `repository_base.py:123` 중첩 체인 로더에 문자열 전달 → SQLAlchemy 2.0 런타임 실패(L-2). 도달불가·테스트부재로 1차에서 보류.
- 결정: 각 중첩 단계를 `attr.property.mapper.class_` 로 해석해 InstrumentedAttribute 전달. **동작 변경**(도달불가 경로 정상화). 검증 확보 위해 격리 declarative Base 로 Parent/Child/GrandChild 관계 모델 + 회귀 테스트 2개 신설(단일/중첩, expunge 후 접근으로 지연로딩 부재 검증).
- 변경 후: mypy 4→3(line 123 해소, 잔여는 SQLAdmin 스텁 3), tests 67→**69 passed**. app Base.metadata 오염 없음(격리 Base).
- 검증: ruff/format clean, 신규 테스트 2 pass, 전체 69 pass.
- 관계: **대체**(1차 "보류" 결정을 명시적 근거[검증 확보]로 뒤집음). 회귀 없음.

**작업 L-4 · `4d39216` fix(middleware): CORS 최외곽 등록**
- 변경 전: `bootstrap.create_app` 에서 CORS 를 user_info 보다 먼저 등록 → CORS 가 내측. 에러 응답 CORS 헤더 미보장(L-4).
- 결정: 등록 순서 역전(user_info → CORS)으로 CORS 최외곽화. **동작 변경**(저위험).
- 변경 후: tests 69 passed(엔드포인트 조립·요청 정상).
- 검증: ruff/format clean, 전체 69 pass.
- 관계: 신규. 회귀 없음.

**최종 상태**: ruff clean · mypy **3**(SQLAdmin formatter 스텁 부정확, 상류 한계) · bandit(비테스트) 0 · tests **69 passed**. 보류 잔여 2건(배포 HOST env 주입, 템플릿 방향) = 소유자 결정.

---

## 실행 #1 (후속 2) — 2026-07-08 · 남은 보류 처리 + 최종 bandit 감사

소유자 지시: "알려준 내용 진행 + 모든 단계 후 bandit 감사, **nginx 설정 가능 항목 제외**".
- **item 1(HOST 바인딩/외부 노출)** = nginx 리버스 프록시 계층 항목 → **제외**(기존 B104 안전 기본값 유지, 코드 변경 없음).
- **item 2(템플릿 정합성)** = 진행. 미사용 믹스인은 **동작 보존이 검증되는 범위(정의 정확 일치)** 에서 채택. BaseRepository 재사용 스캐폴딩은 템플릿 가치상 제거하지 않음(유지).

**작업 L-3 · `7880165` refactor(models): 믹스인 채택**
- 변경 전: `UUIDMixin`/`TimestampMixin` 정의만 되고 미사용, 5개 모델이 동일 `id`/`created_at` 인라인 중복 선언(불일치).
- 결정: 인라인 정의가 믹스인과 **정확 일치**함을 5개 모델 전부 확인 후 상속 전환. `id` 는 UUIDMixin, `created_at` 은 TimestampMixin, `updated_at`(믹스인 없음)은 인라인 유지. home 은 updated_at 없음.
- 회귀 위험 검수: `Base.id: Mapped[Any]` 타입 선언(1-B)과 믹스인 상속의 상호작용을 user 모델 1개로 선검증(9 tests) 후 확산 → SQLAlchemy 매핑 충돌 없음.
- 변경 후: **동작 보존**(컬럼 타입/PK/default/nullable 동일, 물리 컬럼 순서만 변경·ORM 무영향). tests **69 passed**, mypy 3 유지, ruff clean.
- 관계: 보완(L-3 해소). 회귀 없음.

**최종 bandit 감사 (nginx 계층 제외)**
- 전체: Low 68 / Medium 0 / High 0. **68건 전부 테스트 파일 B101(assert) = 오탐**.
- **비테스트 실이슈 0건**. B104(host bind)는 (a)이미 안전 기본값으로 수정됨 + (b)외부 노출은 nginx 계층 담당이라 제외 대상.
- nginx 계층 항목(외부 바인딩/TLS/보안 헤더/rate limit)은 애플리케이션 범위 밖으로 제외.
- **결론**: 애플리케이션 코드 보안 스캔 클린.

**최종 상태(전체)**: ruff clean · ruff format clean · mypy **3**(SQLAdmin 스텁 한계) · bandit 비테스트 **0** · tests **69 passed**(베이스라인 67 + 신규 회귀 2). 보류 잔여 = 배포 HOST env(nginx 계층·제외), 템플릿 스캐폴딩 축소 여부(소유자 결정).

---

## 실행 #1 (후속 3) — 2026-07-08 · 재사용 표면 전수 검증 (A-1 해소)

소유자 원칙 제기: "재사용 가치가 있으려면 실제로 범용 동작해야 한다. 특정
조건에서만 되면 재사용 가치 없음." → 미검증 표면을 유지/축소 취향 문제가 아니라
**검증 문제**로 재정의. 옵션 (A) 검증 패스 선택.

**작업 · `baade53` test(repository): 재사용 표면 전수 검증**
- 변경 전: BaseRepository 의 18개 메서드가 앱 미사용·테스트 0 → 미검증(잠재 함정). L-2 가 실제 그 상태에서 깨져 있던 증거.
- 결정: 격리 모델(Item/Tag: 관계·Text·Integer 컬럼)로 18개 메서드 전수 호출 검증. 통과=재사용 확정 / 실패=수정 or 제거.
- 검증 대상: bulk_create, get_many, exists, exists_by, get_by_id_with, get_one_with, get_many_with, get_by_ids_with(빈목록 조기반환 포함), get_partial, get_by_id_partial, get_in_batches, get_with_join, count_with_relation, bulk_update, update_by, bulk_delete, delete_by, get_or_create, update_or_create.
- 결과: **18/18 통과**. L-2(기수정) 외 **추가 결함 없음**. 표면 전체가 이제 검증됨 → **제거 불필요**(A-1 (a) 유지가 정당화됨).
- 인지 사항(한계): 검증 환경은 기존 스위트와 동일한 **aiosqlite**. 프로덕션 **MySQL(aiomysql)** 방언 특이사항(예: 특정 group_by/collation)은 범위 밖 — 단, L-2 부류(쿼리 구성/API 오용) 결함은 커버됨.
- 검증: tests **69→87 passed**, ruff/format clean, mypy 3 유지.
- 관계: 보완(A-1 결정 근거 확보). 회귀 없음.

**A-1 결론**: 재사용 표면이 검증됨으로써 "미검증 스캐폴딩" 우려 해소. 유지가 정당(파괴적 축소 불필요). 소비자는 격리 테스트(`test_repository_crud_surface.py`)를 사용 예시로 참고 가능.



