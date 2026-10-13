# Residual Risk — access-policy (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-501 | 가드는 "선언이 있는가·모순이 없는가" 만 본다 — 잘못 고른 수준(관리 경로에 `Public`, 의도치 않은 `PublicWrite`)은 통과한다. | MED | ADR-002. 수준 선택은 사람의 판단이다. 예시 경로는 `tests/test_authorization.py` 의 `EXPECTED` 가 고정하고, `PublicWrite` 는 이름 자체가 리뷰에서 눈에 띄도록 분리했다. | 2026-10-13 | 새 기능이 늘어 리뷰로 감당이 안 되면 `PublicWrite` 사용 위치 허용 목록 같은 추가 검사를 검토한다. |
| R-502 | 소유권(작성자 본인 또는 슈퍼유저)은 선언이 아니라 서비스의 `OwnershipPolicy` 호출이다 — 수정·삭제 뷰가 `LoginRequired` 만 선언하고 서비스에서 판정을 빠뜨려도 가드는 막지 못한다. | MED | ADR-004·ADR-005. 소유 판정은 엔티티 조회 뒤에야 가능해 선언으로 표현할 수 없다. 예시 기능은 실요청 테스트(`test_other_user_cannot_modify` 등)가 고정한다. | 2026-10-13 | 소유 리소스가 많아지면 서비스 기반 클래스에 판정 훅을 두는 방안을 검토한다. |
| R-503 | 검사 대상은 FastAPI `APIRoute` 다. Starlette `Route`·`WebSocketRoute` 를 앱에 직접 붙이거나 다른 ASGI 앱을 `Mount` 하면 검사 밖이다. | LOW | 명세 §2 — 문서 `Route` 와 `/admin` `Mount` 는 의도적 제외. 저장소에 WebSocket 은 없다. | 2026-10-13 | WebSocket 이나 새 Mount 를 도입하면 charter 를 개정해 대상에 넣는다. |
| R-504 | 판정은 의존성 **함수의 동일성**으로 한다 — `get_current_principal`·`require_superuser` 를 감싼 새 의존성(예: 자체 `get_current_user`)은 내부에서 원래 함수를 `Depends` 로 쓰면 트리로 인정되지만, 같은 일을 다른 함수로 다시 구현하면 선언으로 보지 않는다(기동 거부 쪽으로 실패). | LOW | ADR-002. 실패 방향이 "거부" 라 안전하고, 오류 메시지가 선언 방법을 안내한다. | 2026-10-13 | 인증 방식이 늘면(API 키 등) 그 의존성을 `AccessLevel` 에 등록한다. |
| R-505 | `app.dependency_overrides` 로 인증 의존성을 바꿔도 판정은 원래 트리로 한다 — 테스트에서 override 해도 가드 결과는 같다. | LOW | 의도된 동작. 가드는 배포될 선언을 본다. | 2026-10-13 | — |

<!--
규칙:
- 여기 있는 항목을 다음 라운드에서 새 finding 으로 다시 올리지 않는다.
- 재평가 조건이 참이 되면 ledger 로 승격한다(그때 비로소 "결함").
-->
