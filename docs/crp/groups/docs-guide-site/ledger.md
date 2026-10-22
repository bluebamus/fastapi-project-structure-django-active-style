# Ledger — docs-guide-site (지적 원장)

> 지적 ID 는 2차 검수 지적표(active)의 것을 그대로 쓴다. 커밋: `362eafe`(생성물 원본) · `a275ad1`(트랜잭션·흐름·인증·기능) ·
> `043d1c3`(시작·설정·API·테스트·배포) · `ad25277`(허브·README) · `487375f`(docstring·`.env.example`·ARCHITECTURE) · `86a066a`(계약 테스트).

| ID | Severity | 결정 | Status | 커밋 | 고친 것 |
|---|---|---|---|---|---|
| FT-01 | HIGH | Fix | **Fixed** | `a275ad1` | 기능 8편: 쓰기 View 가 응답 DTO 검증 뒤 `await service.commit()` 1회, 서비스·저장소는 commit 안 함 |
| AR-01 | HIGH | Fix | **Fixed** | `a275ad1` | architecture: 트랜잭션 경계는 쓰기 View, 계층 책임 표 |
| SD-01 | HIGH | Fix | **Fixed** | `a275ad1` | sequence-diagrams 쓰기 도식(렌더·원문): DI 가 writer 세션, View 가 DTO 검증 → commit, 예외는 close 의 ROLLBACK |
| SD-02 | MED | Fix | **Fixed** | `a275ad1` | 인가 도식: 토큰 없음·무효 401, su 아님 403 |
| SD-03 | LOW | Fix | **Fixed** | `a275ad1` | lifespan = Redis PING·버전, background 정리 등록, DEBUG create_all, worker 는 별도 프로세스 |
| GS-01 | MED | Fix | **Fixed** | `043d1c3` | 설정 검사는 config import 시점 |
| GS-02 | MED | Fix | **Fixed** | `043d1c3` | 부팅 도식: lifespan 은 Redis·DEBUG create_all, /ready 는 요청마다 SELECT 1·PING |
| GS-03 | MED | Fix(지적 일부 정정 — 감독 정정) | **Fixed** | `043d1c3` | Redis 필수(기동 거부). 요청 중 장애 503 은 Redis 를 쓰는 경로만 — `tests/e2e/test_faults.py` 가 Redis 정지 중 blog 목록 200 을 확인 |
| GS-04 | MED | Fix | **Fixed** | `043d1c3` | 비밀 키 3종(32자+, access≠refresh)·`MYSQL_PASSWORD` 교체, Redis 기본값은 그대로 |
| GS-05 | MED | Fix | **Fixed** | `043d1c3` | DEBUG=true 면 MySQL 필요, `scripts.create_superuser` |
| AR-02 | MED | Fix | **Fixed** | `a275ad1` | 규약 6개 표, `AppContractError`, `AccessPolicyGuard` 기동 거부 |
| AR-03 | LOW | Fix | **Fixed** | `a275ad1` | 조립 순서: ready 훅·모델 import·Celery tasks |
| API-01 | MED | Fix | **Fixed** | `043d1c3` | `/docs`·`/openapi.json` 은 DEBUG=true 만 |
| API-02 | LOW | Fix | **Fixed** | `043d1c3` | rate limit 은 register·login 만, 접근 수준은 Guard 이름, 소유권은 "추가 규칙" 열 |
| CFG-01 | MED | Fix | **Fixed** | `043d1c3` | 설명을 Field description 에서 — 오배치 제거 |
| CFG-02 | HIGH | Fix | **Fixed** | `043d1c3` | 설정 검사 표(출처·비밀 키·비밀번호·배포 조합·옛 ADMIN) |
| CFG-03 | MED | Fix | **Fixed** | `043d1c3` | Settings 전 필드(75개), 주석 처리 설정 표시 |
| CFG-04 | LOW | Fix | **Fixed** | `043d1c3` | 새 비밀 설정은 `LOG_SECRET_SETTINGS` 등록 |
| CFG-05 | LOW | Fix | **Fixed** | `043d1c3` | 값 잘림 없음(CORS_ALLOW_METHODS 전체) |
| RP-01 | MED | Fix | **Fixed** | `a275ad1` | request id 삭제 → client IP·UA·경로·상태·처리 시간 |
| RP-02 | MED | Fix | **Fixed** | `a275ad1` | 미들웨어 순서, 오류 변환 표(Redis 503) |
| RP-03 | LOW | Fix | **Fixed** | `a275ad1` | DEBUG=true 면 다시 던짐 |
| RP-04 | LOW | Fix(사실 정정) | **Fixed** | `a275ad1` | routed 세션은 승인된 특수 경로 전용 — 지적의 "이 저장소는 일부 사용"과 달리 기능 코드 사용 0(`tests/core/test_session_dependency_names.py`) |
| AU-01 | MED | Fix | **Fixed** | `a275ad1` | access 15분 전 회수 불가, /me 외는 클레임만 |
| AU-02 | LOW | Fix | **Fixed** | `a275ad1` | 재사용 → family 폐기 401, 비활성·삭제 사용자 refresh 거부 |
| FT-02 | MED | Fix | **Fixed** | `a275ad1` | AuthService → RefreshTokenStore 직접 |
| FT-03 | MED | Fix | **Fixed** | `a275ad1` | 본인 수정 is_active·is_superuser 403, 변경·삭제 시 refresh·관리 세션 폐기 |
| FT-04 | LOW | Fix | **Fixed** | `a275ad1` | 보존 삭제(beat 03:30, 5,000행), sink 등록(apps.ready), tasks.py 소스 |
| DV-01 | MED | Fix | **Fixed** | `a275ad1` | 생성기 명령·규약 파일·변수 이름 |
| DV-02 | LOW | Fix | **Fixed** | `a275ad1` | `test_api_matrix.py` 의 `OPS`·`test_inventory.py` 대조 |
| DV-03 | LOW | Fix | **Fixed** | `a275ad1` | 도식 노드 "Service: 업무 규칙", View 가 commit |
| TS-01 | MED | Fix(명령 정정) | **Fixed** | `043d1c3` | `python -m pytest -m "not mysql"` — 지적의 `and not browser` 는 이 저장소에 없는 마커(pyproject markers·ci.yml gate) |
| TS-02 | MED | Fix | **Fixed** | `043d1c3` | mysql·compose.test.yaml, e2e 는 `-m e2e` 일 때만, CI 세 job·skip 0 |
| TS-03 | LOW | Fix | **Fixed** | `043d1c3` | 인증·rate limit 은 fakeredis 단위 테스트 |
| OP-01 | MED | Fix | **Fixed** | `043d1c3` | request id 삭제 → route template·시각·user_id |
| OP-02 | MED | Fix(지적 일부 정정 — 감독 정정) | **Fixed** | `043d1c3` | Redis 장애: 기동 차단, 실행 중은 Redis 경로 503·/ready 503, 나머지 조회는 응답(GS-03 과 같은 근거) |
| OP-03 | MED | Fix | **Fixed** | `043d1c3` | ENV 게이트, Secure 쿠키 → HTTPS, TRUSTED_PROXY_HOPS, beat, 첫 슈퍼유저 |
| OP-04 | LOW | Fix | **Fixed** | `043d1c3` | URL → MYSQL_*/REDIS_* 개별 키(URL 은 ALEMBIC_DATABASE_URL 만) |
| HUB-01 | LOW | Fix | **Fixed** | `ad25277` | README 링크 복원 |
| HUB-02 | LOW | Fix | **Fixed** | `ad25277` | sequence-diagrams 를 새 문서 카드로 |
| HUB-03 | LOW | Fix | **Fixed** | `ad25277` | 줄 단위 서식·끝 개행 |
| RR-01 | LOW | Fix | **Fixed** | (이 기록 커밋) | docs-guide-review residual-risk 를 main 내용으로 되돌리고 해결 기록만 덧붙임 |
| CM-01 | LOW | Fix | **Fixed** | `a275ad1`·`043d1c3`·`ad25277` | mermaid@11.12.0 고정 + CDN 실패 안내, 라벨 정정(ADR-002) |
| 부수-1 | LOW | Fix | **Fixed** | `487375f` | "e2e-policy-2 결정 N" 15개 파일 → integration-e2e ADR-009/013/010/011/012·V-003/V-006 (CRP 기록은 그대로) |
| 부수-2 | LOW | Fix | **Fixed** | `487375f` | `user_access_log_service` docstring — commit 은 쓰기 핸들러·access_log_sink |
| X-01 | LOW | Fix(지적 밖) | **Fixed** | `487375f` | `.env.example` 의 없는 `admin-auth-guide.html` → `workflows/admin-authentication.html` |

## Round 2 — 2차 재검수 남은 결함 (2026-10-22, round2-report)

| ID | 심각도 | 처리 | 상태 | 커밋 | 근거·비고 |
|---|---|---|---|---|---|
| FT-01 정정 | MED | 정정 기록 | **1차 Fixed 는 일부만** | — | reports 도식(렌더·원문)에 commit 간선이 남았다 → A-N1 |
| FT-03 정정 | MED | 정정 기록 | **1차 Fixed 는 일부만** | — | "권한 바뀌면 폐기" 표현이 남았다(활성화·승격은 유지) → A-N2 |
| 부수-1 정정 | LOW | 정정 기록 | **1차 Fixed 는 일부만** | — | `tests/core/test_mysql_auth_dependency.py` 인용이 남았다 → A-N6. 1차 Round 1 의 "전부 Fixed · CONVERGED" 는 이 세 건만큼 사실과 달랐다 |
| A-N1 | MED | Fix | **Fixed** | `7be79b3` | `features/reports.html` 도식의 commit 간선 삭제 — `sales_reports.py` GET 하나, read-only 세션 |
| A-N2 | MED | Fix | **Fixed** | `7be79b3` | 세션 폐기는 비활성화·강등·비밀번호 변경·삭제만(`user_service.revocation_for`) — user·features 허브 |
| A-N3 | LOW | Fix | **Fixed** | `7be79b3` | Redis 장애 503 대상 한정(`tests/e2e/test_faults.py` outcomes·blog 목록 200) |
| A-N4 | LOW | Fix | **Fixed** | `7be79b3` | deployment "모든 ENV" → test 외(`config.validate_deployment_safety`) |
| A-N5 | MED | Fix(테스트) | **Fixed** | `eda2049` | `test_feature_api_tables_match_openapi_and_access_policy` — 복사본 변이 PublicWrite→Public 에서 실패 |
| A-N6 | LOW | Fix | **Fixed** | `7be79b3` | docstring 인용 → integration-e2e ADR-014 |
| A-N7 | LOW | Fix | **Fixed** | `7be79b3` | 접속 로그는 `ACCESS_LOG_ENABLED` + 제외 경로·확장자 아닌 요청(`user_info_middleware._should_skip`) — home·features 허브 |
| X-2 | LOW | Fix(테스트) | **Fixed** | `eda2049` | 링크 `#fragment` 실재 검사(HTML id·name, MD 제목 slug) — 복사본 변이 HTML·MD 앵커에서 실패 |

## Round 3 — 검수 루프 라운드 2: 반복 지적 거시 재진단 (2026-10-22)

원인: 폐기 **규칙**(`revocation_for` — 비활성화·강등·비밀번호 해시 변경, 삭제는 `DELETED`)을 **진입점** 목록처럼 옮겨 적었다. HTTP `PATCH` 의 `UserUpdate` 는 email·is_active·is_superuser 뿐이고 관리 화면 폼은 해시를 노출하지 않는다 — 비밀번호 해시 변경의 진입점은 CLI `create_superuser --set-password`(Redis 실패 = 종료 코드 2) 하나다. 처방: 규칙 정본은 `features/user.html#revocation` 표 한 곳, 다른 곳은 링크 또는 진입점 기준 서술. 저장소 전체 grep('비밀번호 변경'·'503'·'폐기')으로 사실 단위 판정.

| ID | 심각도 | 처리 | 상태 | 커밋 | 근거·비고 |
|---|---|---|---|---|---|
| A-N2 정정 | MED | 정정 기록 | **Round 2 Fixed 는 사실과 달랐다** | — | 도식·요약에 '비밀번호 변경' 을 HTTP 경로처럼 넣었다 → R2-A |
| A-N3 정정 | LOW | 정정 기록 | **Round 2 Fixed 는 사실과 달랐다** | — | authentication 503 대상에 '비밀번호 변경' 이 들어갔다(HTTP 경로 없음, CLI 는 종료 코드 2) → R2-A |
| R2-A | MED | Fix | 수정됨 — 검수 대기 | `24f7a63`·`f5e6fb5` | 정본 표 `features/user.html#revocation`(규칙 + 어디서 일어나나). user 요약 2·핵심 패턴·도식 렌더/원문·features 허브·authentication 503 범위·README 465/467/610/651·ARCHITECTURE 744. 코드 주석: create_superuser 12·149, user/admin.py 123·147, user_service 모듈 docstring, refresh_store.revoke_user, e2e test_ops 134, test_create_superuser 210 |
| R2-A 확인만 | — | 확인 | 맞음 — 고치지 않음 | — | DEVELOPMENT.md:570·admin-authentication.html:372 '새 서비스(예: 비밀번호 변경)' 는 가정 예시. admin-authentication 327·352 는 이미 진입점 구분('폼은 노출하지 않는다'). getting-started 100·deployment 73 '사용자 수정·삭제의 세션 폐기' 는 사실. CRP 다른 그룹 기록은 append-only 이력이라 손대지 않음 |
| A-C1 / N-2 | MED | Fix(테스트) | 수정됨 — 검수 대기 | `74c483c` | `test_configuration_table_matches_settings_fields` — 이름 집합 == model_fields, 중복 행 금지, 코드 기본값·description 일치(말로 적은 값: 없음/빈 값/config.API_DESCRIPTION 명시 목록). 기존 이름 부분 문자열 검사를 대체 |
| A-C2 | LOW | Fix | 수정됨 — 검수 대기 | `f5e6fb5` | `user_info_middleware` 모듈 docstring·`.env.example` ACCESS_LOG_ENABLED 주석 → `_should_skip`(활성 + 제외 경로·확장자 아님). README·ARCHITECTURE §7.1·config API_DESCRIPTION·가이드는 이미 맞음 |

## Round 4 — 검수 루프 라운드 3: 폐기 정본을 코드에서 닫는다 (2026-10-22)

원인(거시 재진단 2, 위치 키 `features/user#폐기` 3회째): 정본 표의 "어디서 일어나나" 를 사람이 진입점을 떠올려 나열했다 — 경로가 새로 보일 때마다(관리 화면 → CLI → 로그인 재해시) 표가 틀어졌다. 처방: 표를 `revoke_user_access` 를 **호출하는 모듈**(AST 로 닫힌 사실 — `user_service.py`·`admin.py`·`scripts/create_superuser.py`)로 다시 정의하고 `tests/test_docs_guide_site.py` 로 고정. 그 밖의 해시 변경(로그인 bcrypt→Argon2 재해시, `auth_service` `verify_and_update`)은 비밀번호가 그대로라 폐기하지 않는다고 경계를 적었다.

| ID | 심각도 | 처리 | 상태 | 커밋 | 근거·비고 |
|---|---|---|---|---|---|
| R2-A 정정 | MED | 정정 기록 | **Round 3 의 "진입점은 CLI 하나" 서술은 좁지 않았다** | — | "비밀번호 해시 변경 … CLI 만" 은 로그인 재해시(해시는 바뀌나 폐기 없음)를 빠뜨렸다. 표의 진입점 열은 관리 화면 모듈(`admin.py`)을 소스 경로로 적지 않았다 → R3-REV |
| R3-REV | MED | Fix + 계약 테스트 | 수정됨 — 검수 대기 | `76df541`·`9b76c66` | `features/user.html#revocation` = 판정 표(변경 → refresh·관리 세션) + 실행 위치 표(호출 모듈 3개, 판정 `revocation_for`/`DELETED`/CLI 둘 다) + 경계 문장 + "명시적 비밀번호 교체는 CLI `--set-password` 뿐". `test_revocation_section_lists_exactly_the_revoke_callers` — 절의 소스 경로 집합 == AST 호출 모듈 집합 |
| A-R2-1 | MED | Fix | 수정됨 — 검수 대기 | `08337b9` | 로그아웃 = 지금 세션 하나(`admin_auth.logout` → `session.clear()`, 미들웨어 `_commit` 이 그 SID `store.delete`, DB 커밋 무관) / 강등·비활성화·삭제·CLI 비밀번호 교체 = 그 사용자의 관리 세션 전부(`revoke_user`, 커밋 전). README 465·ARCHITECTURE 789·admin-authentication 개요 표 '폐기' 행 |
| A-R2-1 확인만 | — | 확인 | 맞음 — 고치지 않음 | — | ARCHITECTURE 742('로그아웃·authenticate 거부는 키를 지우고' — 그 세션 키), admin-authentication 166·222·270/279·284·356(세션 단위 서술), `admin_session.py` 모듈 docstring 4(복사 쿠키 무효 — 사용자 전체라고 하지 않음) |
