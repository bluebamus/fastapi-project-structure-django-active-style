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



