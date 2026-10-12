# Run Log — service-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 단계 하나 = Round 하나(Round 0 = 계획).

## 라운드 기록

### Round 0 — 2026-10-12 (base SHA: `4707cd4`) — 계획
- **트리거:** 사용자 요청(REQ-001) — 2026-10-07 리뷰의 우선 조치 1~8 진행, Redis 필수, 로그인 고도화.
- **검수 범위:** 2026-10-07 전체 검수 리뷰의 지적 전수 대조 → 단계 A~F2 에 배정.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **기준선 실측:** `pytest -m "not mysql"` 814 passed / 32 deselected / skip 0 · 22 paths / 37 operations · alembic head `d4e6f8b12c34`.
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 14 · LOW 8 (ledger F-001~F-023)
- **이전 요구 충돌:** orm-raw-repository charter 2-4 의 Redis readiness·JWT lifecycle 비목표와 R-002 의 권한 모델 비목표 → ADR-018 로 대체(그 그룹 design-baseline 에 상태 주석 append). SQLAdmin 비목표(C-8)는 유지(ADR-017).
- **수렴 판정:** `NOT CONVERGED` (Open Fix 23)
- **잔여 위험 변화:** R-201~R-204 등록.

### Round 1 — 2026-10-12 (base SHA: `e357f0c`) — 단계 A
- **트리거:** REQ-001 단계 A(리뷰 우선 조치 1·2 의 DSN·4).
- **검수 범위:** `.github/workflows/ci.yml`, `scripts/review_gate.py`, `config.py`·`migrations/env.py`·DSN 소비처, `app/core/db/router.py`, `app/core/repositories/repository_base.py`·`ProductRepository`·`UserAccessLogRepository`, 관련 가이드 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 에서 등록한 F-001~F-005 를 닫았다)
- **Fix:** F-001 · F-002 · F-003 · F-004 · F-005 → **Fixed**
- **fail-on-revert:** 수정 전 파일을 하나씩 되돌려 새 테스트를 돌렸다 — ci.yml 1 실패 · 게이트 1 실패(보조 가드 2건은 새 분기 고정용 대조군이라 통과) · DSN 8 실패(`config.py`+`env.py`) · 라우터 10 실패 · 정렬 base 3 / product 1 / access log 1 실패. 복원 후 전부 통과.
- **동작이 바뀐 기존 테스트:** `tests/core/test_db_router.py` 의 DSN 문자열 비교 7건을 `make_url(...)` 의미 비교로 바꿨다(속성이 `URL` 객체를 돌려주므로). 단언의 강도는 같다 — 드라이버·사용자·비밀번호·호스트·포트·DB 가 모두 비교된다. 삽입 순서에 기대던 목록 테스트는 없었다.
- **검사 수치:** `pytest -m "not mysql"` 845 passed / 32 deselected / skip 0(814 → +31), `-m mysql --collect-only` 32 수집, ruff check·format 클린, mypy 190 files 0 issues, review_gate `supply`·`docs`·`structure` 통과(static 의 mypy 는 로컬 정책 사유로 별도 실행 — 아래).
- **환경 주석:** 로컬 Windows 의 애플리케이션 제어 정책이 mypy 의 컴파일된 확장(DLL) 로드를 막아 `uv run python -m mypy .` 가 import 단계에서 죽는다. 같은 버전(1.20.2)의 순수 Python 빌드를 작업 폴더 밖 venv 에 설치해 `--python-executable` 로 이 저장소 venv 를 가리켜 실행했다. CI(ubuntu)에는 해당 없다.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 18: F-006~F-023 — 다음 단계)
- **잔여 위험 변화:** 없음.

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 14 | 8 | 23 | NOT CONVERGED |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 5) | NOT CONVERGED |
