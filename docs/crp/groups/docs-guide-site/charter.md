# Charter — docs-guide-site  (Charter v0.1 / 2026-10-22)

> 검수의 닫힌 정의. 상위 기준은 `design-baseline.md` 의 REQ-001.

## 1. 인벤토리

| 영역 | 경로 | 종류 |
|---|---|---|
| 새 HTML 가이드 19편 | `docs/guides/{getting-started,architecture,reference,workflows,features,development,operations}/` 아래 새 파일 | 문서 |
| 허브·스타일 | `docs/guides/index.html`, `docs/guides/assets/style.css` | 문서 |
| 같은 사실 | `README.md`, `docs/guides/ARCHITECTURE.md`, `.env.example` 주석, 코드 docstring·주석 | 문서·주석 |
| 계약 테스트 | `tests/test_docs_guide_site.py` | 테스트 |

- 기준선: main `6f00cf6` · 38 operations.

## 2. 계약

- **코드가 정답이다.** 지적마다 코드 근거를 다시 열고, 지적이 코드와 다르면 코드대로 고친다. 코드 동작은 바꾸지 않는다.
- 같은 사실은 모든 문서에서 같은 값이다. Mermaid 는 렌더 블록과 원문 블록이 같고 `mermaid@11.12.0` 고정.
- HTML 은 줄 단위 서식, 태그 짝 오류 0, 끝 개행. 저장소 격리.

## 3. 합격 기준

- ledger 의 Fix 전부 Fixed. 계약 테스트는 수정 전 실패 → 수정 후 통과.
- `.env` 없는 클론에서 `pytest -m "not mysql"` 통과(skip 0), ruff check·format, 링크 검사 broken 0, `review_gate --group docs` 통과.
