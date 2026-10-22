# Design Baseline — docs-guide-site (기준 설계 문서)

> 이 그룹의 요구사항·설계 결정의 단일 기준. append-only — 항목은 지우지 않고 상태만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [ ] **보통(Balanced)**
- [x] **간략(Lean)** — 사용자가 "지적 전부"로 범위를 정했고 지적 목록이 항목을 고정했다.

선택: **간략** · 선택일: 2026-10-22

## 1. 목적 / 배경

main `6f00cf6` 위에 생성된 HTML 가이드 사이트(새 19편·허브·style.css)를 검수한 지적 43건(검수 39 + 감독 1 + 부수 2 + 공통 정리)을
코드에 맞춘다. 생성물은 사용자가 커밋을 승인했으므로 원본을 먼저 커밋하고 그 위에 고친다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-22 | "1번으로 지적 전부 고쳐줘" | ① 생성물 원본 커밋 ② 지적 전부를 코드 근거로 수정(틀린 지적은 코드대로) ③ 내용 계약 테스트 4종 ④ docstring 의 결정 인용·트랜잭션 문구 정정 | 완료 | ledger 전체 |

## 3. 설계 결정 기록 (ADR)

### ADR-001 생성 HTML 은 코드에서 표를 뽑아 다시 쓴다
- 결정: API 표는 `app.openapi()` × `AccessPolicyGuard().operations()`, 설정 표는 Settings 의 `model_fields`(기본값·description)와
  `.env.example` 에서 만든다. 손으로 옮긴 표가 접근 수준·설정 누락·설명 오배치를 만든 원인이었다.
- 계약: `tests/test_docs_guide_site.py` 가 같은 출처로 문서를 대조한다(API 집합 동일, 설정 이름 전수, Mermaid 버전 하나, 허브 링크·스타일시트).

### ADR-002 "CODE-VERIFIED" 라벨은 "PROJECT GUIDE" + 기준 커밋 footer 로 바꾼다
- 이유: 라벨이 붙은 채 코드와 다른 문장이 있었다. 검증 사실(기준 커밋·대조 방법)만 적는다.
