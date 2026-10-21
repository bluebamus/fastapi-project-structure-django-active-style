# Ledger — docs-guide-review (지적 원장)

> 지적 ID 는 가이드 검수 보고서의 것을 그대로 쓴다. 커밋: `0dd3db2`(ARCHITECTURE·DEVELOPMENT) ·
> `e2e3125`(HTML 안내서 3종) · `4655a3a`(README).

| ID | Severity | 판정 | 결정 | Status | 커밋 | 고친 것 |
|---|---|---|---|---|---|---|
| A-01 | MED | OUTDATED | Fix | **Fixed** | `0dd3db2` | §13 CI 세 job(gate·mysql·e2e), 명령 표에 `-m e2e` |
| A-02 | MED | OUTDATED | Fix | **Fixed** | `0dd3db2` | 글로벌 핸들러 5종(§3·§9), §9 표에 Redis 503 행 |
| A-03 | MED | MISSING | Fix | **Fixed** | `0dd3db2` | §3 도식에 422 문서 후처리·`answer_unhandled_exception`·`AccessPolicyGuard` |
| A-04 | LOW | WRONG | Fix | **Fixed** | `0dd3db2` | §7 미들웨어 순서 `answer_unhandled_exception` → UserInfo → CORS |
| A-05 | LOW | WRONG | Fix | **Fixed** | `0dd3db2` | §1 Settings 12종 → 9종, 설정 검사 3종 |
| A-06 | LOW | MISSING | Fix | **Fixed** | `0dd3db2` | §1 트리에 `compose.e2e.yaml`·`tests/e2e`·`create_superuser.py`·`access.py`·`admin_session.py` |
| A-07 | LOW | INCONSISTENT | Fix | **Fixed** | `0dd3db2` | §4.3 "두 검사" → 세 검사 |
| A-08 | LOW | MISSING | Fix | **Fixed** | `0dd3db2` | §4.3 표에 `LogSettings` validator 3개·`SessionSettings._idle_within_max_age`·`validate_renamed_settings` |
| A-09 | LOW | WRONG | Fix | **Fixed** | `0dd3db2` | §2.1 `order-items` 는 발견·import 되고 `router.py` 가 있으면 `AppContractError` |
| A-10 | LOW | WRONG | Fix | **Fixed** | `0dd3db2` | §5 필터 순서를 핸들러별로(콘솔·`--logfile` / 큐 / 파일) |
| A-11 | LOW | MISSING | Fix | **Fixed** | `0dd3db2` | §10.3 `create_superuser --set-password` 폐기·종료 코드 2 |
| A-12 | LOW | MISSING(일부) | Fix | **Fixed** | `0dd3db2` | §9 AppException 행에 headers(401 `WWW-Authenticate`·429 `Retry-After`)만 추가 — 재검수 범위 |
| A-13 | LOW | UNCLEAR | Fix | **Fixed** | `0dd3db2` | §8.2 `background_db_session()` 의 except rollback |
| A-14 | MED | MISSING | Fix | **Fixed** | `0dd3db2` | §13 본문에 e2e 마커·`compose.e2e.yaml`·수집 조건 |
| D-01 | MED | WRONG | Fix | **Fixed** | `0dd3db2` | §3 생성기가 `api/routers/v1/<name>.py`(예시 `GET /ping`, include 전 미서빙)를 만든다 |
| D-02 | LOW | BROKEN-LINK | Fix | **Fixed** | `0dd3db2` | §13 링크 텍스트 옛 파일명 → `workflows/*.html` |
| D-03 | LOW | MISSING(일부) | Fix | **Fixed** | `0dd3db2` | §11 e2e 실행 방법(compose 기동·`pytest -m e2e`·필요한 변수) — README 정본(ADR-002) |
| S-01 | MED | MISSING | Fix | **Fixed** | `e2e3125` | #redis·#requests·#health 에 요청 중 Redis 503·예외 미들웨어(로그 1회·keep-alive·DEBUG 재던짐)·422 광고 |
| S-02 | LOW | INCONSISTENT | Fix | **Fixed** | `e2e3125` | 설정 검사 세 개, 실제 호출 순서로 나열 |
| S-03 | LOW | MISSING | Fix | **Fixed** | `e2e3125` | 레벨 도식에 `_min_level`·`AppLevelFilter`, 표 한 행 |
| S-04 | LOW | INCONSISTENT | — | **판정 보류(고치지 않음)** | — | 재검수가 ARCH §7.1 의 대응 문장을 특정하지 못함. 관련 사실 "모든 핸들러에 RedactingFilter" 는 A-10 과 함께 코드대로 고침(`e2e3125`) |
| S-05 | LOW | OUTDATED | Fix | **Fixed** | `e2e3125` | 기준일·최종 갱신 2026-10-21, 기준 main `f8291f2` |
| S-06 | LOW | MISSING | Fix | **Fixed** | `e2e3125` | #app-assembly 에 `AccessPolicyGuard`, #log-sinks 에 fork 뒤 queue listener 재시작 |
| H-01 | LOW | BROKEN-LINK | Fix | **Fixed** | `e2e3125` | 줄 번호 근거를 함수·블록 이름으로(ADR-001) |
| H-02 | LOW | WRONG | Fix | **Fixed** | `e2e3125` | 미들웨어 도식 순서(바깥부터) |
| H-03 | LOW | MISSING | Fix | **Fixed** | `e2e3125` | `SESSION_SECRET_KEY` 소비처 ③ 로그 마스킹(`LOG_SECRET_SETTINGS`) |
| F-01 | MED | OUTDATED | Fix | **Fixed** | `e2e3125` | /admin 서명 세션 쿠키 → Redis 서버 세션(meta description 포함) |
| F-02 | MED | OUTDATED | Fix | **Fixed** | `e2e3125` | ProductUpdate 는 `PatchSchema` — 명시 null 422 |
| F-03 | MED | WRONG | Fix | **Fixed** | `e2e3125` | D-01 과 같은 사실 |
| F-04 | LOW | WRONG | Fix | **Fixed** | `e2e3125` | 22/37 → 23/38 |
| F-05 | LOW | INCONSISTENT | Fix | **Fixed** | `e2e3125` | Redis 오류 계약을 DEVELOPMENT §9 와 같게 |
| F-06 | LOW | INCONSISTENT | Fix | **Fixed** | `e2e3125` | "dependencies.py 만" → `dependencies.py`·`access.py` |
| F-07 | LOW | INCONSISTENT | Fix | **Fixed** | `e2e3125` | 옛 파일명 `server-lifecycle-guide.html` |
| F-08 | LOW | MISSING | Fix | **Fixed** | `e2e3125` | CI e2e job, 체크리스트에 e2e `OPS` |
| R-01 | LOW | WRONG | Fix | **Fixed** | `4655a3a` | README API 표 22/37 → 23/38 (F-04 와 같은 사실) |
| R-02 | LOW | OUTDATED | Fix | **Fixed** | `4655a3a` | README 테스트 절 CI 두 job → 세 job (A-01) |
| R-03 | LOW | OUTDATED | Fix | **Fixed** | `4655a3a` | README 권한 표 아래 "서명 세션 쿠키" → Redis 서버 세션 (F-01) |
| R-04 | LOW | WRONG | Fix | **Fixed** | `4655a3a` | README 로깅 `filters` 행을 핸들러별로 (A-10) |
| R-05 | LOW | WRONG | Fix | **Fixed** | `4655a3a` | README 문제 해결 — 식별자 아닌 디렉터리는 마운트 누락이 아니라 `AppContractError` (A-09) |

## 후속 (2026-10-21, 사용자 "고쳐줘")

| ID | 구분 | 위치 | 내용 | 상태 |
|---|---|---|---|---|
| R-1302 | README | 문서 안내 `docs/crp/groups/` 행 | 빠진 그룹 `access-policy`·`integration-e2e`·`docs-guide-review` 추가 | Fixed |
