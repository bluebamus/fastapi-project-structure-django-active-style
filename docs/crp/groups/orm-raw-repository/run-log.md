# Run Log — orm-raw-repository (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-08-18 (base SHA: `76aed3c1aea2d3f1754f650ba631c8d853562cec`)
- **트리거:** 사용자 요청 REQ-002 — "docs/orm-raw-repository/ 설계·개발계획서를 참고로 작업 진행".
- **검수 범위:** Phase 0 기준선 전수 측정 (코드 변경 없음).
- **GATE 통과:** 0 ☑ 1 □ 2 □ 3 □ 4 □ 5 □
- **측정 결과 (artifact: `baseline/`):**
  - `env.txt` — commit `76aed3c`, branch `main`, Python 3.14.4, `uv.lock` sha256 `d1bc64a8…c9d7b8`,
    `pyproject.toml` sha256 `f4eb895b…22022022`, `alembic heads` = `b2f1a9c0d3e4 (head)` 단일
  - `pytest.txt` — **271 passed** (skip/xfail/deselected 0)
  - `survey.txt` — OpenAPI **18 paths / 30 operations**, 정규화 sha256
    `4ce7f6b6e931358029b265f8946ae931f0d873a92c018f009c6981d8944ae98a`,
    operationId 누락 0 / 중복 0, component schemas 31개
  - `openapi.json` — 정렬 고정 스냅샷(골든)
  - registry 자동 발견 앱 6개 `[auth, blog, home, reply, sns, user]`,
    metadata 테이블 5개 `[blog_posts, replies, sns_posts, user_access_logs, users]`,
    Admin ModelView 5개 `[PostAdmin, ReplyAdmin, SnsPostAdmin, UserAccessLogAdmin, UserAdmin]`
  - `CRUDBase` 메서드 4개(`_get/_add/_update/_delete`), `BaseRepository` 공개 메서드 28개
  - CI: `.github/workflows/ci.yml` 에 pytest + skip/xfail 0 게이트 존재, **MySQL service 없음**,
    `compose.test.yaml` 없음, `scripts/` 에 `review_gate.py` 없음(`new_app.py` 만 존재)
  - SQL 로깅: `session.py:82,111,170` 모두 `echo=False` (redaction 미구현 → R-007)
  - `/admin`: `authentication_backend` 미주입 (`app/features/admin.py:71` 주석만) → F-006
- **신규 finding(심각도별):** CRIT 0 · HIGH 3 · MED 3 · LOW 1
- **신규 Fix(계약 위반):** 7 건 → ledger F-001 ~ F-007
- **수렴 판정:** `NOT CONVERGED` (Open Fix 7건, Phase 1~9 미착수)
- **잔여 위험 변화:** R-001 ~ R-007 최초 등록.
- **깊이 주석:** 이번 라운드는 *측정·기록 전용*이며 소스 코드를 변경하지 않았다. F-001~F-007 은
  모두 계획서가 사전 예고한 항목이며, 실제 코드 위치를 확인해 확정한 것이다(신규 발견이 아니라 확증).
  F-004(모듈 경로형 스키마명 2건)와 F-005(tags 불일치)는 계획서에 개수·대상이 명시돼 있지 않았고
  이번 측정에서 처음 구체적으로 특정했다.

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 3 | 1 | 7 | NOT CONVERGED |
