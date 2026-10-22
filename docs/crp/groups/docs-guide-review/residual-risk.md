# Residual Risk — docs-guide-review (잔여 위험 등록부)

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-1301 | S-04 "예외 로그 보증 표현이 ARCH §7.1 과 어긋남" — 대응 문장을 특정하지 못해 판정 보류. 관련 사실(마스킹 필터 위치)은 고쳤다. | LOW | 재검수 판정 보류(명세 — 고치지 않는다) | 2026-10-21 | 어긋나는 두 문장이 특정되면 ledger 로 올린다. |
| R-1302 | README "문서 안내" 의 `docs/crp/groups/` 목록에 최근 그룹(access-policy·integration-e2e 등)이 빠져 있다 — 이번 지적과 다른 종류라 고치지 않았다. | LOW | 명세 — 새로운 종류의 검수는 하지 않고 보고만 | 2026-10-21 | 다음 문서 정리 때 목록을 갱신한다. |

## 해결 기록

| ID | 해결 내용 | 근거 |
|---|---|---|
| R-1302 | README 문서 안내의 CRP 그룹 목록에 `access-policy`·`integration-e2e`·`docs-guide-review` 를 더했다. | commit `68dd6f4` |
