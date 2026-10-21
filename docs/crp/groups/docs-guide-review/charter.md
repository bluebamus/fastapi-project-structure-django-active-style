# Charter — docs-guide-review  (Charter v0.1 / 2026-10-21)

> 검수의 닫힌 정의. 상위 기준은 `design-baseline.md` 의 REQ-001.

## 1. 인벤토리

| 영역 | 경로 | 종류 |
|---|---|---|
| 레퍼런스 | `docs/guides/ARCHITECTURE.md`, `docs/guides/DEVELOPMENT.md` | 문서 |
| HTML 안내서 | `docs/guides/index.html`, `docs/guides/workflows/server-lifecycle.html`·`admin-authentication.html`·`feature-development.html` | 문서 |
| 개요 | `README.md` | 문서 |

- 기준선: main `f8291f2` · 라우트 인벤토리 23 paths / 38 operations(`tests/test_route_inventory.py`).

## 2. 계약

- **코드가 정답이다.** 문서만 고친다. 코드·테스트 동작은 바꾸지 않는다.
- 같은 사실은 모든 문서에서 같은 값이다. 정본이 따로 있으면 링크로 줄인다.
- HTML 은 `html.parser` 로 태그 짝 오류 0, Mermaid 는 기존 형식, 줄바꿈(CRLF) 보존.
- 저장소 격리 — 다른 저장소를 언급·비교하지 않는다.

## 3. 합격 기준

- ledger 의 Fix 전부 Fixed, 판정 보류는 이유와 함께 남긴다.
- `tests/test_doc*.py` 통과, 링크·앵커 검사 broken 0, `review_gate --group docs` 통과.
