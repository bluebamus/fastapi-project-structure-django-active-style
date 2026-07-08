# AUDIT_REPORT.md — 전체 코드베이스 감사 보고서

- **저장소**: fastapi-project-structure-django-active-style (Django 스타일 자동 앱 발견 FastAPI 구조 템플릿)
- **실행일**: 2026-07-08
- **브랜치**: `audit/full-review-2026-07-08` (base `main` @ 21f7a64)
- **패키지 매니저**: uv · 런타임: Python 3.14.4(uv venv) · 대상: 135개 소스 파일
- **상세 작업 이력·회귀 검수 표**: [`AUDIT_LEDGER.md`](AUDIT_LEDGER.md) 참조(append-only 원장)

---

## 1. 요약

| 지표 | 값 |
|---|---|
| 베이스라인 테스트 | 67 passed / 0 failed |
| 최종 테스트 | **69 passed / 0 failed** (회귀 0, 신규 회귀테스트 2 추가) |
| 적용한 수정 | ruff format(57파일) · mypy 49→**3** · bandit B104 · 중첩 eager-loading(L-2) · 미들웨어 순서(L-4) |
| 보류(소유자 결정) | 2건 (배포 HOST env 주입 · 템플릿 방향) — 아래 §4 |
| 커밋 | 5개 원자적 커밋 (`0220eba`,`8bc17be`,`cb384b2`,`9f11513`,`4d39216`) + 문서 |
| 설치 도구 | **bandit** (uvx 임시 실행, 의존성 미영구화). ruff·mypy 는 기존 dev 의존성. |

> **후속 처리**: 소유자 "진행" 지시로 1차 보류 4건 중 코드로 안전·검증 가능한 **L-2(중첩 eager-loading + 회귀테스트), L-4(미들웨어 순서)** 를 적용 완료. 잔여 2건(배포 HOST, 템플릿 방향)은 소유자 결정 영역이라 코드 변경 없이 유지.

**총평**: 매우 잘 설계된 코드베이스다. 3계층 경계·async 일관성·트랜잭션 경계·예외/로깅이 견고하고, 문서(README)와 실제 아키텍처가 대체로 일치한다. 실제 결함은 정적 타입/보안 소수에 그쳤고 모두 안전하게 수정했다. 남은 항목은 대부분 "재사용 스캐폴딩" 성격의 설계 판단 사항이다.

정적 검사 최종 상태: `ruff check` clean · `ruff format` clean · `mypy` **3건**(문서화된 SQLAdmin 스텁 한계) · `bandit`(비테스트) 0건.

---

## 2. 심각도별 발견 목록

### High
- 없음.

### Medium
- **[M-1] 보안 · B104 (수정 완료)** — `main.py:15` 개발서버 `host="0.0.0.0"` 하드코딩(모든 인터페이스 바인드).
  - 조치: `app_settings.HOST/PORT` 로 이전, 기본값 로컬 전용 `127.0.0.1`. `.env.example` 에 키/설명 추가. 커밋 `cb384b2`.
  - **동작 변경(보안 하드닝)**: `python main.py` dev 서버가 기본 localhost 바인드. 배포 노출은 `HOST=0.0.0.0` env 주입 필요(§4 참조). README 문서 실행(`uvicorn --host 0.0.0.0`)에는 영향 없음.

### Low
- **[L-1] 타입 정확성 (수정 완료)** — `mypy` 49건. 실제 해결(타입 힌트·시그니처 보강, 런타임 무변경)으로 **49→4**(커밋 `8bc17be`), 이후 L-2 수정으로 **최종 3**.
  - `filters.py:42` `frame` 을 `FrameType | None` 로 명시(None 역참조 표현 정확화)
  - `pagination.py` `T`→`BaseModel`(model_fields), `ModelT`→`Base`(model.id)
  - `models_base.py` `Base` 에 매핑 안 되는 `id: Mapped[Any]` 선언(모든 모델의 `id` 불변식을 제네릭 Repository 계약에 반영, 전체 테스트로 무영향 검증)
  - `repository_base.py` DML 결과를 `CursorResult` 로 cast(rowcount/no-any-return)
  - `user_info_middleware.py` `ASGIApp`/`RequestResponseEndpoint` 정합
  - `task.py` `run_async` 제네릭화 → celery task 반환 타입 정합
  - routers ×5 `responses` 상수 타입 주석 / mypy override `celery.*`
- **[L-2] 중첩 eager-loading 결함 (수정 완료)** — `repository_base.py:123` 중첩 `.selectinload(<str>)` 가 SQLAlchemy 2.0 에서 문자열 인자로 실패(`relations=["a.b"]` 사용 시). 현재 앱은 relationship 0 이라 도달 불가였으나 재사용 스캐폴딩이므로 수정. 각 중첩 단계를 관계 대상 매퍼 클래스에서 해석하도록 변경 + 격리 모델 회귀 테스트 2개 추가. 커밋 `9f11513`, mypy line 123 해소, tests 67→69.
- **[L-3] 미사용 믹스인** — `models_base.py` `UUIDMixin`/`TimestampMixin` 정의되나 도메인 모델은 상속 대신 `id`/`created_at` 인라인 선언. 경미한 불일치. §4 참조(템플릿 방향과 함께).
- **[L-4] 미들웨어 순서 (수정 완료)** — CORS 가 `user_info` 보다 내측(먼저 등록)이라 에러 응답 CORS 헤더 미보장. 등록 순서를 역전해 CORS 최외곽화. 커밋 `4d39216`, tests 69 passed.

> 참고: bandit Low 68건은 전부 테스트 파일의 `assert`(B101) 오탐. 프로덕션 코드에 assert 없음.

---

## 3. 설계 정합성 검수 결과

### 3.1 파악한 저장소 목적·핵심 설계
`app/domains/*` 디렉터리 컨벤션을 스캔해 앱(라우터/모델/Admin)을 **자동 발견**하는 FastAPI 구조 템플릿. 3계층(Router→Service→Repository→DB), **UnitOfWork 미사용**·기능 의존성 기반 트랜잭션 경계, MySQL(async aiomysql)+Redis+Celery+SQLAdmin+Scalar. 문서는 충실(README 42KB + docs/).

### 3.2 정합성 대조 (코드 ↔ 의도)
| 항목 | 결과 | 근거 |
|---|---|---|
| 자동 앱 발견 | ✅ 구현·동작 | `registry.discover/import_models`, `/api` 마운트 |
| 3계층 경계 | ✅ 준수 | 라우터에 DB/비즈니스 로직 없음, 서비스→repository |
| 트랜잭션 경계(UoW 미사용) | ✅ 일치 | `get_<name>_service` yield 후 commit, 예외 시 롤백 |
| 엔드포인트 문서 | ✅ 일치 | README 표 ↔ 실제 경로(home 5종 검증, 4도메인 CRUD 동일) |
| 실행/환경변수 | ✅ 일치 | `uv sync`/`uv run uvicorn`, env 키 일치 |
| **N+1 Eager Loading "내장"** | ⚠️ **드리프트(부분 잔존)** | 중첩경로 결함은 수정(L-2)했으나, 앱 모델에 relationship 0·호출자 0 → 여전히 미검증(미사용) 기능. 템플릿 방향 판단 필요(§4-2) |

### 3.3 설계·워크플로우 평가
관심사 분리·응집도 양호, 순환 의존 없음. 설정/시크릿은 Pydantic Settings+env 로 일관 관리, 예외 핸들러 4종(민감정보 DEBUG 게이팅), 로깅 구조화, async 일관, lifespan 이 백그라운드 태스크 drain 후 엔진 dispose. 커넥션 풀을 메인/백그라운드로 분리해 고갈 방지. **경미**: 미들웨어 순서(L-4).

### 3.4 문서-코드 불일치 처리 내역
| 불일치 | 기준 채택 | 근거 |
|---|---|---|
| N+1 Eager Loading 광고 vs 미사용/결함 | **판단 보류(양쪽 자동변경 안 함)** | 코드에 API 는 실재(문서가 틀린 것 아님) + 최근 커밋이 README 를 코드에 맞춰 능동 정합화 중. 편집적 톤 변경은 소비자 결정 영역 → §4 권고 |

### 3.5 회귀 방지 비교 표
과거 실행 없음(원장 신규). 본 실행 내부 회귀 없음 — 상세는 [`AUDIT_LEDGER.md` §5.6.2](AUDIT_LEDGER.md) 참조.

---

## 4. Human Decision / 설계 결정 필요 목록

> 1차 §4의 4건 중 **L-2(중첩 eager-loading)·L-4(미들웨어 순서)** 는 소유자 "진행" 지시로 수정 완료(§2). 아래는 **소유자 결정이 남은 항목**이다.

1. **[배포] HOST 값 주입 (M-1 후속)** — B104 수정으로 dev 서버 기본이 `127.0.0.1`. **컨테이너/원격 배포 시 `HOST=0.0.0.0` 을 env 로 주입**해야 외부 노출됨(`.env.example` 에 명시). README 의 `uvicorn --host 0.0.0.0` 실행에는 영향 없음.
   - 권고: 배포 매니페스트/컨테이너 env 에 `HOST=0.0.0.0` 추가. (코드 아님 — 배포 설정)

2. **[템플릿 방향성 — 미사용 표면 + 미사용 믹스인, L-3 관련]** — `BaseRepository` 의 eager-loading/bulk/upsert/partial/join/batch 다수가 미사용이고 앱 모델에 relationship 이 없음. `UUIDMixin`/`TimestampMixin` 도 미사용. (L-2 수정으로 중첩 로더는 이제 정상 동작하나, 여전히 앱 내 소비처는 없음.)
   - 권고(택1): (a) 재사용 스캐폴딩으로 유지하되 README 에 "관계 정의 시 사용" 전제를 명시하고 relationship 예제 추가, 또는 (b) 표면을 실제 사용 메서드 중심으로 축소하고 미사용 믹스인 제거. — 템플릿 방향성에 대한 소유자 판단.

3. **[mypy 잔여 3건 — 프레임워크 스텁 한계]** — `admin.py`(home) `column_formatters` lambda 3건은 SQLAdmin 이 formatter 첫 인자를 `type` 으로 선언한 **스텁 부정확**(SQLAdmin 공식 예제 `lambda m, a: m.name[:10]` 도 동일 실패). 억지 우회(`# type: ignore`/`getattr`) 대신 문서화.
   - 권고: 상류 SQLAdmin 타입 개선 대기, 또는 admin 표시 계층에 한해 별도 mypy 완화 정책 결정.

---

## 5. 다음 단계 제안

- **CI 게이트 도입**: `ruff check` + `ruff format --check` + `mypy`(잔여 3건은 baseline 처리) + `bandit -r app --skip B101`(테스트 assert 오탐 제외) + `pytest` 를 PR 게이트로.
- **pre-commit**: ruff(check+format), mypy, bandit 훅 등록으로 회귀 조기 차단.
- **bandit 설정 영구화**: `pyproject.toml [tool.bandit]` 에 `exclude_dirs=["tests"]`, `skips=["B101"]` 를 명시해 팀 공통 기준 고정(현재는 uvx 임시 실행).
- **테스트 보강**: (2) 수정 시 relationship 픽스처 기반 eager-loading 회귀 테스트, CORS 프리플라이트/에러응답 헤더 테스트.
