# Run Log — access-policy (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-10-13 (base SHA: `3880451`) — 계획·조사
- **트리거:** 사용자 요청 REQ-001(예시 뷰의 인증 적용 범위와 기본 정책을 뷰 단위·데코레이터로).
- **검수 범위:** `main.py` 조립부, `app/core/registry.py`(라우터 결선), `app/core/security/*`, 8개 기능의 `api/routers/v1/*.py`, `tests/test_authorization.py`, `scripts/new_app.py`, 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **조사:** 예시 뷰의 보호 방식이 셋(인자 `CurrentPrincipal`, 경로 `dependencies=[Depends(require_superuser)]`, home·reports 의 라우터 단위 `APIRouter(dependencies=...)`)이고 공개 뷰는 표시가 없다. main 이 registry 결선 뒤에 `/health`·`/ready`·`/docs`(DEBUG, `include_in_schema=False` 인 `APIRoute`)를 붙인다 — 가드 호출 지점은 그 뒤여야 한다(ADR-003). FastAPI 0.141 에서 `fastapi.routing.iter_route_contexts(app.routes)` 가 `_IncludedRouter` 를 펼쳐 prefix·의존성이 합쳐진 effective context(경로·`dependant`)를 준다 — 라우터 단위 의존성이 트리에 들어옴을 실측했다.
- **신규 finding:** CRIT 0 · HIGH 0 · MED 1 · LOW 3 (F-001~F-004) · 해당 없음 1(F-005)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-13 — REQ-001 구현
- **Fix:** F-001 · F-002 · F-003 · F-004 → **Fixed**
- **설계:** ADR-001(경로 데코레이터 `dependencies=[...]`, 감싸는 데코레이터 없음), ADR-002(`AccessPolicyGuard`), ADR-003(main 조립 끝), ADR-004(예시 정책 현재 동작 유지), ADR-005(권한표 하나), ADR-006(스캐폴드 예시 뷰는 include 하지 않음).
- **동작이 바뀐 기존 테스트:** `tests/test_authorization.py::test_every_operation_is_classified` 를 `test_example_routes_declare_expected_access_levels` 로 바꿨다 — "모든 operation 이 분류됐는가" 는 기동 검사가 대신하고(선언 없는 뷰가 있으면 `main` import 자체가 실패), 예시 정책 표(`EXPECTED`, 공개/공개쓰기/로그인/슈퍼유저)와 가드 판정·OpenAPI `security` 표시를 대조한다. 소유자 분류(OWNER)는 선언이 아니라 서비스 동작이라 표에서는 `LoginRequired` 이고 같은 파일의 소유권 실요청 테스트가 그대로 고정한다. 그 밖의 기존 테스트는 바꾸지 않았다.
- **OpenAPI 불변:** 변경 전(main `3880451` 의 `git archive`)과 후의 `json.dumps(app.openapi(), sort_keys=True)` 가 바이트 단위로 같다(88,604 bytes, `DEBUG=true ENV=test`).
- **DB 접속 없음:** 새 테스트는 lifespan 을 돌리지 않는다. 조립 경로 검사는 서브프로세스에서 `import main` 만 한다.

### fail-on-revert (Round 1)
대상 파일을 작업 폴더 밖에 복사해 두고 결함을 되살린 내용을 넣어 돌린 뒤 복사본으로 복원했다.

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| `main.py` 의 `AccessPolicyGuard().verify(app)` 를 `pass` 로 | `tests/core/test_access_policy.py` | 1 failed(`test_main_refuses_to_assemble_with_an_undeclared_route`) |
| 스캐폴드 템플릿의 `dependencies=[Public]` 제거 | `tests/scripts/test_new_app.py` | 1 failed(생성 결과가 가드 통과) |
| 가드의 의존성 트리 재귀 제거(직계만) | `test_access_policy.py`·`test_authorization.py` | 수집 오류 2 — 실제 앱 조립이 위반으로 멈춤(`/me` 의 `get_current_user` 아래 `get_current_principal` 을 못 봄) |
| superuser 우선 판정 제거(`elif` → `if`) | `test_access_policy.py` | 수집 오류 — `SuperuserRequired` 뷰가 이중 선언으로 판정돼 실제 앱 조립이 멈춤 |
| 쓰기+`Public`·안전+`PublicWrite` 검사를 끔 | `test_access_policy.py` | 6 failed |
| catalog 목록 GET 의 `dependencies=[Public]` 제거(선언 누락) | `test_authorization.py`·`test_access_policy.py` | 수집 오류 2 — `main` import 가 `AppContractError`(GET /api/v1/catalog/products 선언 없음)로 실패 |

### 검사 수치 (최종)
- `pytest -m "not mysql"`: **1190 passed / 43 deselected / skip 0**(1166 → +24: 가드 단위·앱 23, 스캐폴드 1; 권한표 테스트는 1↔1 교체) — 저장소 안, 그리고 `.env` 없는 저장소 밖 클론(`git clone --branch feat/access-policy`) 양쪽 같은 결과. `-m mysql --collect-only`: 43 수집(변화 없음). MySQL 실행은 CI 몫.
- ruff check·format 클린. mypy(순수 Python 빌드 1.20.2, `--python-executable` .venv) 203 files 0 issues.
- `scripts/review_gate.py`: structure·supply·docs 통과(static 은 같은 도구를 개별 실행, deps 는 네트워크 단계라 생략). alembic heads `a7c3e9f1b2d4` 단일 — 리비전 추가 없음.
- **수렴 판정:** `CONVERGED` — Open Fix 0.
- **잔여 위험 변화:** R-501~R-505 등록. log-redaction-fixes R-406(기본 거부 없음) 해소.
