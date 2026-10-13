# Design Baseline — access-policy (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-13 · 변경 이력:
- 2026-10-13: 최초 선택 = 보통. 사유 — 사용자가 "적절하게 판단하여" 정하라고 위임했고, 감독자가 해석(경로
  데코레이터의 `dependencies=[...]` + 기동 시 기본 거부)과 예시 정책(현재 동작 유지)을 정해 사용자에게 설명했다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

예시 뷰마다 인증을 거는 방식이 제각각이었다(핸들러 인자 `CurrentPrincipal`, 경로 `dependencies=[Depends(require_superuser)]`,
라우터 단위 `APIRouter(dependencies=...)`, 공개 뷰는 아무 표시 없음). 공개 뷰에 표시가 없으니 "공개로 정한 뷰" 와
"선언을 잊은 뷰" 를 코드에서 구별할 수 없었고, 막아 주는 장치는 OpenAPI 를 훑는 권한표 테스트 하나뿐이었다
(log-redaction-fixes R-406 — 새 operation 을 PUBLIC 으로 분류하면 통과, `include_in_schema=False` 는 검사 밖).
이 그룹은 접근 수준을 뷰 단위로 **명시**하게 하고, 명시하지 않은 뷰가 있으면 서버가 뜨지 않게(기본 거부) 한다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "현재 프로젝트의 view들은 예시들이다. 때문에 적절하게 판단하여 인증 적용 범위와 기본 정책을 설정해줘. 이는 데코레이터로 충분히 적용할 수 있는 것으로 알고 있다. 뷰 단위 설정으로 고려해줘." (원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합은 주입, 모든 단계 단위 테스트·fail-on-revert) | ① 접근 수준 4개(`Public`·`PublicWrite`·`LoginRequired`·`SuperuserRequired`)를 경로 데코레이터 `dependencies=[...]` 에 선언 ② 기본 정책 = 선언 없는/모순 뷰가 있으면 기동 거부(한 클래스) ③ 예시 뷰 전체에 뷰 단위 선언, 동작·OpenAPI 불변 ④ 중복 권한표 정리(예시 정책 회귀 테스트 1개만) ⑤ 스캐폴드 템플릿 ⑥ 문서 | Active | ADR-001~ADR-006 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-13 | **"데코레이터로 적용" 은 경로 데코레이터의 `dependencies=[...]` 에 접근 수준을 선언하는 것이다.** 함수를 감싸는 Django 식 `@login_required` 는 만들지 않는다. `app/core/security/access.py` 가 `Public = Depends(public)`·`PublicWrite = Depends(public_write)`(아무것도 하지 않는 고유 표식 함수)와 `LoginRequired = Depends(get_current_principal)`·`SuperuserRequired = Depends(require_superuser)`(기존 의존성 그대로)를 공개한다. 핸들러 인자 `CurrentPrincipal`·`SuperuserPrincipal` 도 같은 의존성이라 선언으로 인정한다(중복 표기 강제 안 함). | FastAPI 는 뷰 시그니처로 주입·검증·OpenAPI 를 만든다 — 감싸면 셋이 깨진다. `dependencies=[...]` 는 FastAPI 가 원래 제공하는 "뷰 단위 선언" 자리다. 표식 의존성은 인자가 없어 런타임 비용·OpenAPI 변화가 없다. 기존 의존성을 그대로 쓰므로 401/403 동작과 OpenAPI `security` 가 바뀌지 않는다. | Active | — |
| ADR-002 | 2026-10-13 | **기본 정책은 기동 시 검사로 만든다.** `AccessPolicyGuard`(한 클래스)가 `fastapi.routing.iter_route_contexts(app.routes)` 로 FastAPI 0.141 의 `_IncludedRouter` 중첩까지 펼친 모든 `APIRoute`(숨긴 경로 포함)의 의존성 트리(`dependant`)를 재귀로 훑어 수준을 판정한다. 위반 = (a) 선언 없음 (b) 수준 둘 이상 (c) 쓰기 메서드에 `Public` (d) 안전한 메서드(GET·HEAD·OPTIONS)에 `PublicWrite`. `require_superuser` 는 내부에서 `get_current_principal` 을 쓰므로 둘 다 있으면 슈퍼유저 하나로 판정한다. 문서용 Starlette `Route`(`/openapi.json`)와 `Mount`(`/admin` — 자체 세션 인증)는 대상이 아니다. `verify(app)` 는 위반 전체를 담은 `AppContractError`(registry 의 기존 기동 계약 예외)로 멈춘다. | 데코레이터만으로는 "선언을 잊은 뷰" 가 열린 채 배포된다. 미들웨어 기본 인증은 공개 뷰마다 예외 목록이 필요하고 OpenAPI 와 어긋난다. 조립 결과 전체를 보는 기동 검사는 registry 가 붙인 라우터·main 이 직접 붙인 `/health`·`/ready`·`/docs` 를 함께 덮는다. `iter_route_contexts` 의 effective context 는 include prefix·의존성을 합친 경로·트리를 준다(실측: 라우터 단위 `dependencies` 가 트리에 들어온다). `AppContractError` 를 재사용해 "잘못된 계약은 기동 거부" 관례를 한 예외로 유지한다. | Active | — |
| ADR-003 | 2026-10-13 | **호출 지점은 `main.py` 의 조립 끝(라우터·헬스·문서·Admin 결선 뒤) 한 줄**이다. registry 안에 두지 않는다. | registry 결선 뒤에도 main 이 `/health`·`/ready`·`/docs` 를 붙인다 — registry 안에서 검사하면 그 셋을 놓친다. 모듈 import 시점에 돌기 때문에 lifespan(DB·Redis)과 무관하게 `uvicorn main:app`·테스트의 `from main import app` 모두에서 막힌다. | Active | — |
| ADR-004 | 2026-10-13 | **예시 정책은 현재 동작을 유지한다**(감독자 판단): blog·sns·reply 조회 `Public`, 작성·수정·삭제 `LoginRequired`(인자 principal, 수정·삭제는 서비스 `OwnershipPolicy`) · catalog 조회 `Public`, 쓰기 `SuperuserRequired` · reports·access-logs 전부 `SuperuserRequired` · users 목록·생성·삭제 `SuperuserRequired`, 단건 조회·수정 `LoginRequired`(+ 본인 판정) · auth register·login·refresh·logout `PublicWrite`, `/me` `LoginRequired`(`get_current_user` 가 `CurrentPrincipal` 을 씀) · `/health`·`/ready`·`/docs` `Public`. home·reports 의 라우터 단위 `dependencies=[Depends(require_superuser)]` 는 뷰 단위로 옮겼다(`responses=FORBIDDEN_RESPONSES` 는 라우터에 남김). | 사용자 요구 "뷰 단위". 라우터 단위 선언도 판정에는 인정되지만 예시는 한 방식으로 통일한다. `/docs` 는 DEBUG 전용 Scalar 페이지로 `include_in_schema=False` 인 `APIRoute` 라 검사 대상이다. 변경 전후 `app.openapi()` 직렬화가 바이트 단위로 같음을 확인했다(run-log). | Active | — |
| ADR-005 | 2026-10-13 | **권한표는 하나만 둔다.** `tests/test_authorization.py` 의 `POLICY`(공개/인증/소유자/슈퍼유저 + OpenAPI 전수 대조, `test_every_operation_is_classified`)를 `EXPECTED`(라우트별 기대 접근 수준) + `test_example_routes_declare_expected_access_levels`(가드의 `operations()` 판정과 대조, OpenAPI `security` 표시도 대조)로 바꾼다. "모든 operation 이 분류됐는가" 는 기동 검사가 맡는다. 401/403·소유권 실요청 테스트는 그대로 둔다. `OWNED` 는 소유권 테스트의 요청 데이터라 분류표가 아니므로 유지한다. | 뷰 선언이 정본이 됐으므로 같은 분류를 다른 표에 또 적으면 두 벌이 된다. 다만 예시 정책이 의도대로인지(누가 `Public` 으로 바꿨는지)는 회귀로 고정해야 한다. 소유자 판정은 선언이 아니라 서비스 동작이라 표의 수준은 `LoginRequired` 이고 동작은 실요청 테스트가 본다. | Active | — |
| ADR-006 | 2026-10-13 | **스캐폴드는 `api/routers/v1/<name>.py` 예시 뷰(`GET /ping`, `dependencies=[Public]`)를 생성하되 `router.py` 에서 include 하지 않는다.** 템플릿 docstring 과 CLI 안내에 "선언하지 않으면 서버가 기동하지 않는다" 를 적는다. | 생성 즉시 include 하면 tags_metadata 양방향 검사·라우트 인벤토리 골든이 사용자 저장소에서 바로 깨진다(기존 스캐폴드는 라우트를 만들지 않았다). 예시 파일이 있어야 "생성 결과가 가드를 통과한다" 를 의미 있게 시험할 수 있다. | Active | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 접근 수준 선언은 경로 데코레이터의 `dependencies=[...]`(또는 같은 의존성을 쓰는 핸들러 인자)로만 한다. 뷰 함수를 감싸는 데코레이터를 만들지 않는다 — ADR-001.
- C-2: 판정 규칙의 정본은 `AccessPolicyGuard` 하나다. 테스트·문서는 그 판정을 재사용하고 규칙을 다시 구현하지 않는다 — ADR-002·ADR-005.
- C-3: 가드는 앱 조립의 마지막에 돈다. 라우트를 붙이는 코드는 그 줄보다 위에 둔다 — ADR-003.
- C-4: 예시 뷰의 응답 코드·OpenAPI(`security` 포함)는 바뀌지 않는다 — ADR-004.
- C-5: 권한 분류표는 테스트 안 `EXPECTED` 하나(README 표는 같은 내용의 문서) — ADR-005.
- C-6: 전체 suite skip 0, 테스트는 DB·Redis 에 접속하지 않는다(가드 조립 경로 검사는 `import main` 만 하는 서브프로세스). 동작이 바뀐 기존 테스트는 run-log 에 이유를 적는다.

## 5. 변경 이력
- v0.1 (2026-10-13): 최초 작성. REQ-001, ADR-001~ADR-006, C-1~C-6. log-redaction-fixes R-406 에 상태 주석 append.
