# Charter — followups-2026-11  (Charter v1.0 / 2026-11-12)

> 검수의 **닫힌 정의**. 상위 기준은 `design-baseline.md`.

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 기능 테스트 공용 픽스처 | `app/features/conftest.py` | 테스트 | 신규 `make_feature_client` |
| 기능 테스트 10개 픽스처 | `app/features/*/tests/` | 테스트 | 팩토리 사용으로 교체 |
| 엔진 안전 옵션 가드 | `tests/core/test_hide_parameters.py` | 테스트 | conftest 제외 |
| MySQL 검증 | `tests/mysql/` | 테스트 | CI 전용, 7건 |
| 게이트 | `scripts/review_gate.py`, `tests/scripts/test_review_gate.py` | 소스/테스트 | `mysql` 그룹 |
| CI | `.github/workflows/ci.yml` | 설정 | `mysql` 잡 |
| 수집 설정 | `pyproject.toml` | 설정 | `norecursedirs` |
| 문서 | `README.md`, `docs/DEVELOPMENT.md` | 문서 | |

- 기본 수집 테스트 수: 1273 (이전 1272 + 게이트 테스트 1) · `tests/mysql` 수집: 7

## 2. 계약 (Contract)
### 2-1. 지원 구성
- 평소 `pytest`·`tests` 게이트: SQLite + fakeredis, 외부 서비스 없음.
- `pytest tests/mysql`: `MYSQL_TEST_URL` 이 가리키는 자기 소유의 빈 MySQL 8.4(관리자 권한).
### 2-2. 위협 모델
- 방어한다: 남의 MySQL 에 기본값으로 붙는 일(기본 URL 없음, 변수 없으면 실패).
- 방어하지 않는다: 사용자가 공용 서버 URL 을 직접 주는 경우.
### 2-3. 불변식
- INV-1: 기본 수집에 `tests/mysql` 이 없고 skip·deselect 로 빼지 않는다 → 수집 ID 비교.
- INV-2: `MYSQL_TEST_URL` 없이 `pytest tests/mysql` 은 연결 시도 없이 실패한다 → 실행 확인.
- INV-3: 픽스처 공용화 전후 수집 테스트 ID 가 같다 → 정렬한 ID 목록 diff.
### 2-4. 비목표
- compose 재도입, 로컬 MySQL 실행, 복제 지연·replica 장애 전환 검증.

## 3. 인수 기준
- [x] 전 테스트 실제 실행·통과(skip 0)
- [x] ruff check / format, 게이트 static·structure·supply·docs·files·tests 통과
- [x] INV-1 · INV-2 · INV-3 확인
- [ ] `mysql` 잡이 CI 에서 통과 (로컬 실행 금지 — 첫 CI 실행에서 확인)

## 4. 변경 이력
- v1.0 (2026-11-12): 최초 작성.
