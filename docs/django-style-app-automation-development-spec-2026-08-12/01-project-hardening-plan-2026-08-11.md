# 프로젝트 구조 및 기능 개선 계획

- 작성일: 2026-08-11
- 상태: 실행 결과 반영(2026-08-12)
- 대상: `fastapi-project-structure-django-active-style`
- 기준: README의 구조 원칙과 현재 구현 검토 결과
- 목표: 자동 앱 등록 구조의 장점을 유지하면서 운영 안전성, 보안, 복원력, 검증 체계를 보완한다.

## 실행 결과 요약

이 문서는 2026-08-11 검토 시점의 작업 계획이다. 2026-08-12 기준으로 migration 완전성,
DB 오류 비노출, 접근 로그 보호, registry import 오류 처리, scaffold 안전성, lifespan 정리,
DB routing 및 CI gate가 구현됐다. 관리자 페이지는 인증 backend를 템플릿 기본 기능으로
도입하지 않고 **기본 비활성화**하는 방향으로 최종 결정됐다. API 인증도 후속 범위로
남겼다. 따라서 아래 우선순위는 최초 판단 기록으로 보존하며, 실제 지원 범위와 현재
동작은 README 및 같은 폴더의 `02-django-style-app-discovery-concept-2026-08-12.md`를 기준으로 한다.

| 항목 | 2026-08-12 상태 |
|---|---|
| Alembic 스키마 완전성 | 완료 |
| SQLAdmin 안전한 기본값 | 완료 — 기본 비활성화 |
| SQLAdmin 내장 인증 | 제외 — 로컬 또는 외부 인증 환경에서만 사용 |
| DB 오류 정보 비노출 | 완료 |
| API 인증·인가 | 후속 범위 |
| 접근 로그 보호 | 완료 |
| registry import 오류 판별 | 완료 |
| 앱 생성 스크립트 안전성 | 완료 |
| lifespan 종료 보장 | 완료 |
| 읽기/쓰기 DB routing | 완료 |
| CI 및 회귀 테스트 gate | 완료 |

## 1. 유지할 설계 원칙

- 의존 방향은 `features -> core -> utils`로 유지한다.
- 기능 간 직접 import를 만들지 않는다.
- 자동 발견과 실제 wiring을 분리한다.
- 기능 내부 계층은 `router -> dependency -> service -> repository`를 따른다.
- 세션 수명주기, 백그라운드 작업 격리, 읽기/쓰기 DB 라우팅 같은 기존 기반 기능은 교체보다 보강을 우선한다.
- README를 구조와 사용법의 단일 기준 문서로 유지하고, 상세 원리는 `docs/concepts`에 둔다.

## 2. 권장 우선순위

| 우선순위 | 작업 | 이유 | 선행 조건 |
|---|---|---|---|
| P0 | Alembic 스키마 완전성 확보 | 운영 환경에서 일부 테이블이 생성되지 않을 수 있다. | 없음 |
| P0 | SQLAdmin 인증 및 안전한 기본값 적용 | 현재 설정 조합에서는 관리 CRUD가 인증 없이 노출될 수 있다. | 인증 방식 결정 |
| P1 | 운영 오류 응답에서 DB 내부 정보 제거 | SQL과 드라이버 정보가 외부 응답에 포함될 수 있다. | 없음 |
| P1 | API 인증·인가 경계 확정 | 인증 설정과 스텁은 있으나 실제 보호 정책이 명확하지 않다. | 관리자 인증 설계와 공통화 권장 |
| P1 | 접근 로그 개인정보·프록시 신뢰 정책 보강 | 쿠키, 쿼리 문자열, 전달 헤더를 무조건 저장·신뢰할 위험이 있다. | 배포 프록시 정책 확인 |
| P1 | 자동 발견의 import 오류 판별 강화 | 기능 내부 의존성 오류가 "선택 모듈 없음"으로 오인될 수 있다. | 없음 |
| P2 | 앱 생성 스크립트 안전성 강화 | 잘못된 이름, 경로 이탈, 기존 파일 덮어쓰기를 막아야 한다. | 없음 |
| P2 | lifespan 종료 보장 | 예외 종료 시 작업 drain과 엔진 dispose가 누락될 수 있다. | 없음 |
| P2 | 읽기/쓰기 DB 라우팅 판별 보강 | 잠금 조회와 텍스트 DML이 reader로 갈 가능성이 있다. | 지원할 SQL 범위 결정 |
| P2 | CI 및 회귀 테스트 게이트 구축 | 핵심 위험에 대한 자동 검증과 최소 커버리지 기준이 없다. | 각 수정 작업의 테스트 추가 |
| P3 | Redis·JWT·메일·업로드 등 미완성 범위 정리 | 템플릿 제공 기능과 향후 확장 지점의 경계가 혼재한다. | 제품 범위 결정 |

## 3. 실행 단계

### 단계 0 — 운영 차단 이슈 해소

#### 0-1. 마이그레이션과 ORM 메타데이터 일치

대상 후보:

- `migrations/versions/`
- `app/features/**/models.py`
- `tests/core/test_alembic_metadata.py`

작업:

1. `Base.metadata`의 전체 테이블과 Alembic 적용 결과를 비교한다.
2. 누락된 `blog_posts`, `replies`, `sns_posts`, `users` 테이블을 마이그레이션에 포함한다.
3. 배포 이력이 불명확하므로 기본 전략은 기존 baseline 수정이 아닌 추가 revision으로 한다. baseline이 외부에 배포된 적이 없다고 확인된 경우에만 baseline 재작성안을 선택한다.
4. 빈 DB에 `upgrade head`를 실행한 결과와 ORM 메타데이터가 일치하는 회귀 테스트를 추가한다.

완료 조건:

- `DEBUG=false`인 빈 환경에서도 모든 모델 테이블이 Alembic만으로 생성된다.
- `upgrade head`, `downgrade`가 성공한다.
- 새 migration autogenerate를 수행했을 때 의도하지 않은 schema diff가 없다.

검증:

- 마이그레이션 표적 테스트
- Alembic upgrade/downgrade 스모크 테스트

#### 0-2. 관리자 화면 기본 폐쇄 및 인증

대상 후보:

- `app/core/bootstrap.py`
- 관리자 설정 모듈
- `app/features/**/admin.py`
- 관리자 접근 테스트

작업:

1. `ADMIN` 기본값을 비활성화한다.
2. SQLAdmin에 `AuthenticationBackend` 또는 동일한 역할의 교체 가능한 인증 계층을 연결한다.
3. 운영 환경에서 관리자가 활성화됐지만 인증 backend, 안전한 세션 secret 또는 필수 인증 설정이 없으면 시작 단계에서 실패하게 한다.
4. 관리자 모델의 생성·수정·삭제·내보내기 권한을 역할별로 명시한다.

완료 조건:

- 기본 설정에서 관리자 URL이 노출되지 않는다.
- 미인증 사용자는 관리자 목록과 CRUD에 접근할 수 없다.
- 잘못된 운영 설정은 애플리케이션 시작 전에 명확한 오류로 거부된다.

검증:

- 관리자 비활성화 테스트
- 미인증/인증/권한 부족 접근 테스트
- 운영 설정 검증 테스트

### 단계 1 — 보안 경계 확립

#### 1-1. 오류 응답과 내부 로그 분리

대상 후보:

- `app/core/repositories/repository_base.py`
- `app/core/bootstrap.py`
- 예외 및 로깅 테스트

작업:

1. 저장소 예외에서 `str(e.orig)` 및 원본 DB 오류를 사용자용 detail에 넣지 않는다.
2. 외부 응답에는 안정된 오류 코드와 일반화된 메시지만 제공한다.
3. 원본 예외는 서버 로그에만 남기며 요청 상관관계 ID로 추적 가능하게 한다.
4. debug 모드에서도 비밀값이 섞일 수 있는 원본 SQL/파라미터의 직접 반환은 금지한다.

완료 조건:

- API 오류 응답에 테이블명, SQL, 드라이버 메시지, 접속 정보가 나타나지 않는다.
- 운영 로그만으로 원인 추적이 가능하다.

#### 1-2. API 인증·인가 정책 구현

대상 후보:

- `app/utils/authenticator/auth.py`
- 인증 관련 설정
- 각 feature router/dependency

작업:

1. 예제 공개 API와 보호해야 할 운영 API를 문서와 코드에서 구분한다.
2. 공통 인증 dependency와 권한 검사를 구현한다.
3. 관리자 인증과 API 인증이 같은 사용자 체계를 공유할지, 별도 체계일지 결정해 중복 보안 로직을 피한다.
4. 변경·삭제 API와 접근 로그 조회를 우선 보호한다.

완료 조건:

- 보호 대상별 인증·권한 규칙이 README에 명시된다.
- 인증 없음, 만료 토큰, 권한 부족, 정상 권한 시나리오가 테스트된다.

#### 1-3. 접근 로그 수집 정책 보강

대상 후보:

- 접근 로그 middleware/sink
- 세션 및 proxy 설정
- 접근 로그 테스트

작업:

1. 신뢰 가능한 proxy 목록이 설정된 경우에만 forwarded IP 헤더를 사용한다.
2. 쿼리 문자열과 쿠키에 대한 allowlist 또는 redaction 정책을 적용한다.
3. 하드코딩된 `session_id` 대신 `SESSION_COOKIE_NAME` 설정을 사용한다.
4. 보존 기간, 삭제 방법, 최대 저장량을 운영 정책으로 명시한다.

완료 조건:

- 공격자가 임의 헤더로 원격 IP를 위조할 수 없다.
- 토큰, 비밀번호, 세션 식별자가 원문으로 저장되지 않는다.
- 로그 보존 정책이 설정과 문서에 반영된다.

### 단계 2 — 정확성과 복원력 보강

#### 2-1. 자동 발견 import 실패를 명확히 구분

대상 후보:

- 자동 발견 registry
- registry 테스트

작업:

1. 선택 모듈 자체가 없을 때만 생략한다.
2. 모듈 내부 의존성 import 실패는 원래 traceback과 feature 이름을 포함해 즉시 실패시킨다.
3. router, dependency, admin view 등 발견 결과의 타입과 필수 속성을 검증한다.

완료 조건:

- 선택 파일 부재는 정상 처리된다.
- 선택 파일 내부의 잘못된 import는 숨겨지지 않고 시작 실패로 보고된다.
- 발견 순서가 결정적이며 기존 `_` 제외 규칙을 유지한다.

#### 2-2. 앱 생성 스크립트의 안전성·멱등성

대상 후보:

- `scripts/new_app.py`
- 스크립트 테스트

작업:

1. 앱 이름을 Python 식별자로 사용 가능한 snake_case로 제한한다.
2. 계산된 경로가 `app/features` 내부인지 확인한다.
3. 대상이 존재하면 기본적으로 실패하고 파일을 덮어쓰지 않는다.
4. 덮어쓰기가 꼭 필요하면 명시적인 `--force`와 변경 대상 미리보기를 요구한다.

완료 조건:

- `../`, 절대 경로, 잘못된 식별자가 거부된다.
- 같은 명령의 재실행이 기존 코드를 손상시키지 않는다.

#### 2-3. lifespan 정리 로직 보장

대상 후보:

- `app/core/bootstrap.py`
- background task 관리 코드
- lifespan 테스트

작업:

1. startup 이후 cleanup을 `try/finally`로 감싼다.
2. drain timeout 시 남은 task를 취소하고 회수하는 정책을 정의한다.
3. 예외 종료에서도 DB 엔진 및 기타 자원이 dispose되는지 검증한다.

완료 조건:

- 정상 종료와 예외 종료 모두 동일한 필수 cleanup을 수행한다.
- 종료가 무기한 대기하지 않는다.

#### 2-4. 읽기/쓰기 DB 라우팅 정확성

대상 후보:

- DB routing session
- reader/writer 선택 테스트

작업:

1. `SELECT ... FOR UPDATE`를 writer로 보낸다.
2. 지원하는 textual DML을 명시적으로 판별하거나, 안전하게 writer로 보내는 보수적 정책을 적용한다.
3. flush 이후 sticky writer와 transaction pin 동작을 유지한다.

완료 조건:

- 잠금 조회와 모든 지원 DML이 reader로 전달되지 않는다.
- 일반 읽기, 쓰기 후 읽기, replica 미설정 시나리오가 회귀 테스트를 통과한다.

### 단계 3 — 지속적 품질과 문서 정리

#### 3-1. CI 품질 게이트

작업:

1. CI에서 Ruff, mypy, pytest를 실행한다.
2. 현재 커버리지를 먼저 측정한 뒤 현실적인 최소값을 설정하고 점진적으로 상향한다.
3. P0/P1 항목의 회귀 테스트를 필수 게이트로 둔다.

완료 조건:

- pull request마다 정적 검사와 테스트가 자동 실행된다.
- 마이그레이션, 관리자 인증, 오류 비노출 테스트 실패 시 병합할 수 없다.

#### 3-2. 제공 기능과 확장 지점 구분

작업:

1. Redis, JWT, SMTP, upload, authenticator의 현재 구현 수준을 분류한다.
2. 실제 제공 기능은 최소 동작과 테스트를 갖추고, 향후 확장 지점은 명확히 stub 또는 out-of-scope로 표시한다.
3. 구조·실행·설정의 기준 정보는 README에 반영하고 상세 설계만 별도 concept 문서로 둔다.

완료 조건:

- 설정만 존재하지만 동작하지 않는 기능이 "지원됨"으로 오해되지 않는다.
- README와 코드의 기능 목록이 일치한다.

## 4. 의존성과 병렬 실행

```text
0-1 Migration ───────────────┐
                             ├─> 3-1 CI gate
0-2 Admin auth ─> 1-2 Auth ──┤
                   └> 1-3 Log privacy
1-1 Error boundary ──────────┤
2-1 Registry ────────────────┤
2-2 Scaffold ────────────────┤
2-3 Lifespan ────────────────┤
2-4 DB routing ──────────────┘
                              └─> 3-2 Docs/scope cleanup
```

- 0-1과 0-2는 서로 독립적으로 진행할 수 있다.
- 1-2는 관리자 인증과 공통 인증 모델을 먼저 합의한 뒤 진행한다.
- 2-1부터 2-4까지는 파일 충돌을 확인한 뒤 병렬 구현 가능하다.
- 테스트는 각 작업과 함께 추가하고, CI 구성은 누적된 검증 명령을 고정하는 단계로 수행한다.

## 5. 검증 전략

- 작은 수정마다 전체 테스트를 실행하지 않는다.
- 각 작업 중에는 관련 표적 테스트와 변경 파일 대상 Ruff만 실행한다.
- P0 종료 시 마이그레이션·관리자·설정 테스트와 전체 Ruff를 실행한다.
- 단계 1과 단계 2 종료 시 각각 전체 pytest를 한 번 실행한다.
- 최종 병합 전 Ruff, mypy, 전체 pytest, Alembic 빈 DB upgrade를 한 번에 검증한다.
- 외부 DB나 Redis가 필요한 검증은 별도 integration job으로 분리하고 단위 테스트와 혼합하지 않는다.

## 6. 권장 작업 단위

1. `fix(migrations): align alembic schema with model metadata`
2. `fix(admin): require authenticated secure admin configuration`
3. `fix(errors): prevent database detail leakage`
4. `feat(auth): define and enforce API authorization policy`
5. `fix(access-log): apply trusted proxy and redaction policy`
6. `fix(registry): surface internal module import failures`
7. `fix(scaffold): validate names and prevent overwrite`
8. `fix(lifespan): guarantee resource cleanup on failure`
9. `fix(db-routing): pin locking and textual writes to writer`
10. `ci: enforce static analysis and regression tests`
11. `docs: clarify supported features and extension points`

각 작업 단위는 구현, 표적 테스트, 필요한 최소 문서 변경을 함께 포함한다. 커밋 여부와 실제 커밋 메시지는 실행 시 저장소 정책에 맞춰 결정한다.

## 7. 위험 및 대응

| 위험 | 대응 |
|---|---|
| 기존 배포 DB와 새 migration 충돌 | baseline 배포 여부 확인 후 additive revision을 기본으로 사용한다. |
| 관리자 인증 도입으로 개발 편의 저하 | 개발용 명시적 opt-in 설정을 제공하되 기본값은 폐쇄한다. |
| 인증 정책이 예제 API의 목적을 훼손 | 공개 예제와 보호 API를 분리하고 문서에 경계를 표시한다. |
| 로그 redaction으로 진단 정보 부족 | 민감값은 제거하되 correlation ID와 구조화된 내부 로그를 유지한다. |
| DB 라우팅 판별 범위 확대에 따른 오분류 | 알 수 없는 쓰기 가능 쿼리는 writer로 보내는 보수적 기본값을 사용한다. |
| 한 번에 큰 변경으로 회귀 원인 추적 곤란 | 위 작업 단위대로 작은 변경과 표적 테스트를 유지한다. |

## 8. 범위 제외

- 자동 발견 구조를 수동 등록 방식으로 교체하는 작업
- `features -> core -> utils` 의존 방향 변경
- 기능 간 직접 import 허용
- 예제 도메인의 업무 규칙 전면 재설계
- 현재 검토와 무관한 신규 인프라 또는 프레임워크 도입

## 9. 전체 완료 정의

- P0와 P1 항목이 모두 구현되고 회귀 테스트가 있다.
- P2 항목은 구현되거나, 지원하지 않는 동작으로 명시하고 안전하게 거부한다.
- 빈 운영 DB가 Alembic만으로 정상 구성된다.
- 관리자와 보호 API는 기본적으로 인증 없이 접근할 수 없다.
- 외부 오류 응답과 접근 로그에 민감한 내부 정보가 노출되지 않는다.
- 자동 발견 실패, scaffold 충돌, 예외 종료, DB 라우팅 경계가 테스트된다.
- CI가 정적 검사와 전체 테스트를 강제한다.
- README의 지원 기능 설명이 실제 구현과 일치한다.
