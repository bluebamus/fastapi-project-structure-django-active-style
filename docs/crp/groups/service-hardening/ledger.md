# Ledger — service-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> 출처: 2026-10-07 전체 검수 리뷰(로컬 보고서, 저장소에 커밋하지 않음)의 지적 번호를 `리뷰` 칸에
> 그대로 적는다(R-xx = 그 보고서의 번호, 이 그룹 residual-risk 의 ID 와 무관). 번호 없는 Low 항목은 요지를 적는다.

| ID | Severity | 리뷰 | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | MED | R-14 | INV-1 | Fix | Open | 단계 A1 | CI 가 `uv sync --frozen` — 락 최신성을 보지 않는데 주석은 "어긋나면 실패" 라고 적었다. |
| F-002 | MED | R-17 | INV-2 | Fix | Open | 단계 A1 | 게이트가 작업 트리를 순회해 무시 대상(`.env`·로컬 전용 문서)까지 비밀 스캔·문서 경로 검사에 넣는다. |
| F-003 | MED | R-06 | INV-3 | Fix | Open | 단계 A2 | DSN 을 f-string 으로 조립 — 비밀번호의 `@ / : #` 가 파싱을 깨고, `%` 는 Alembic 보간 오류. Redis URL 도 같다. |
| F-004 | MED | R-10 | INV-4 | Fix | Open | 단계 A3 | ORM `with_for_update()` 가 read-only 가드를 통과하고 replica 로 라우팅된다. |
| F-005 | MED | R-11 | INV-5 | Fix | Open | 단계 A3 | `get_all` 정렬 없음, 정렬하는 쿼리도 `created_at` 단일 키 — offset 페이지에서 중복·누락. |
| F-006 | MED | R-04 | INV-6 | Fix | Open | 단계 B | 신뢰 모드에서 XFF 의 가장 왼쪽 값을 채택 — 클라이언트가 IP 를 위조한다. |
| F-007 | MED | R-03 | 2-2 로그 누출·접속 로그 | Fix | Open | 단계 B | 컬럼보다 긴 헤더·쿠키에서 접속 로그가 조용히 버려진다(MySQL strict). |
| F-008 | MED | R-02 | 2-2 로그 누출 / INV-11 | Fix | Open | 단계 B·F2 | query_string 원문 저장(B), 접속 로그 조회 무인증(F2). |
| F-009 | LOW | 미처리 예외가 접속 로그를 우회 | 2-2 로그 | Fix | Open | 단계 B | `call_next` 에 try 가 없어 500 이 기록되지 않는다. |
| F-010 | LOW | session_id 쿠키 이름 불일치 | 2-2 로그 | Fix | Open | 단계 B | 미들웨어가 `session_id` 를 읽지만 설정 쿠키 이름은 `session` — 항상 NULL. |
| F-011 | LOW | null PATCH → 409, FK 위반 → 500 | 2-1 | Fix | Open | 단계 B | Update 스키마의 명시적 null 이 NOT NULL 위반을 "충돌" 로 응답한다. |
| F-012 | LOW | 리포트 기간 상한 없음 | 2-1 | Fix | Open | 단계 B | `end_date=9999-12-31` 에서 날짜 연산이 NULL 이 되어 빈 결과. |
| F-013 | LOW | 4xx 를 ERROR 로 로깅 | 2-2 로그 | Fix | Open | 단계 B | 클라이언트 오류가 운영 ERROR 로 쌓인다. |
| F-014 | MED | R-19 | C-6 | Fix | Open | 단계 C | 엔드포인트 테스트가 read-only 세션을 표시 없이 대체한다. |
| F-015 | MED | R-20 | 2-1 | Fix | Open | 단계 C | ORM 기능 경로가 MySQL 에서 한 번도 돌지 않는다. |
| F-016 | MED | R-09 | INV-7 | Fix | Open | 단계 D | `DateTime(timezone=True)` 가 MySQL 에서 오프셋·소수 초를 잃는다. |
| F-017 | MED | R-13 | INV-8 | Fix | Open | 단계 E | Redis 필수인데 `/ready` 가 Redis 를 보지 않는다(필수 유지 결정 — ADR-008). |
| F-018 | MED | R-18 | INV-9 | Fix | Open | 단계 E | 중앙 Celery 태스크가 기능을 직접 import, 워커는 registry 를 거치지 않는다. |
| F-019 | MED | R-07 | INV-10 | Fix | Open | 단계 F1 | refresh 회전·폐기와 로그인 rate limit 이 없다. |
| F-020 | LOW | bcrypt 72바이트 절단 | 2-2 | Fix | Open | 단계 F1 | Argon2 이전으로 해소(기존 해시는 기존 규칙으로 검증 후 재해시). |
| F-021 | LOW | `JWT_ALGORITHM` 자유 문자열 | 2-2 | Fix | Open | 단계 F1 | HS 계열 `Literal` 로 제한. |
| F-022 | HIGH | R-01 | INV-11 | Fix | Open | 단계 F2 | 모든 기능 CRUD 가 무인증 — 익명이 계정 정지·이메일 열거. |
| F-023 | LOW | 무인증 POST /users 가 비밀번호 없는 계정 생성 | INV-11 | Fix | Open | 단계 F2 | 생성은 슈퍼유저 전용 + 비밀번호 필수. |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
