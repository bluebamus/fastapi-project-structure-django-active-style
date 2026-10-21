# Checklist — integration-e2e (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-20 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] 병합된 main(`c463ac0`)에서 인벤토리 재추출 — operation·접근 수준·관리 뷰·Celery·Redis 접두어(run-log Round 0)
- [x] 포트 확인(Windows `netstat`·WSL `ss -ltn` 모두 비어 있음), WSL→Windows `127.0.0.1` 전달 확인

## Round 1 — 2026-10-20 REQ-001 (브랜치 `feat/integration-e2e`)
- [x] (W0) Redis 대상 명시 강제·자식 env 명시·CI 대상 명시
- [x] W1 `compose.e2e.yaml`(primary + GTID replica + Redis), W2 하네스, W5 의존성
- [x] (F-001) `pymysql[rsa]`
- [x] L2 매트릭스 38 operation × 7칸 / (F-002) 401 `WWW-Authenticate`
- [x] L3 시나리오 1~8
- [x] L4 관리 화면 7 뷰 브라우저 흐름 / (F-003) 상품 폼 서버 관리 열
- [x] L4 인증·CSRF·로그아웃·세션 폐기·만료·ADMIN_DISABLED·측정 2건
- [x] L5 장애 주입·L6 운영(사용자 결정을 기대값으로)
- [x] W3 인벤토리 대조(빈 칸 0·모르는 Redis 키 0·로그 비밀값 0)
- [x] W6 CI job `e2e`, review gate 의 `E2E_*` 허용
- [x] (P-001) OpenAPI 422 스키마 — Round 3 에서 결정 반영(`7df4a54`)
- [x] (P-002) `create_superuser --set-password` 세션 폐기 — Round 3 에서 결정 반영(`c8758ed`)

## Round 2 — 2026-10-20 REQ-002 (사용자 결정)
- [x] (F-004) Redis 연결 장애 503·traceback 한 번·연결 유지
- [x] (F-005) read-only 읽기의 replica 연결 오류 → primary 한 번 재시도 + WARNING
- [x] (F-006) 기동 초기 줄 프로세스별 파일(uvicorn·python main.py·worker·beat 확인)
- [x] W7 README·ARCHITECTURE·DEVELOPMENT
- [x] Windows·Linux(`.env` 없는 WSL 네이티브 클론) 전체 재실행
- [ ] (P-003) 그 밖의 처리되지 않은 500 의 traceback 중복·연결 종료 — 사용자 결정 대기

## Round 3 — 2026-10-21 REQ-003 (브랜치 `fix/e2e-policy-2`)
- [x] 결정 1 OpenAPI 422 = `ErrorResponse`(`7df4a54`)
- [x] 결정 2 처리되지 않은 500 의 traceback 한 번·keep-alive — ① 미들웨어로 직접 받기(`626e506`)
- [x] 추가 결정: 의존성 `aiomysql[rsa]` 로 통일(`d214d24`)
- [x] 결정 3 모든 401 `WWW-Authenticate: Bearer` — 이미 충족, 계약 테스트(`02018e4`)
- [x] 결정 4 `create_superuser --set-password` 세션 폐기·fail-closed(`c8758ed`, mypy 후속 `cc34570`)
- [x] 결정 5 인증 사용자 조회 primary(`bea5b38`)
- [x] 결정 6 관리 화면 Redis 장애 모두 503 — 이미 충족, 계약 테스트(`af46062`)
- [x] 결정 7 CSRF 폼 본문 상한 413·필드 400(`341f584`)
- [x] README·ARCHITECTURE·관리 인증 안내서 갱신
