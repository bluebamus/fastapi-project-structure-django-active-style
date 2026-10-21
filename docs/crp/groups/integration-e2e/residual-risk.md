# Residual Risk — integration-e2e (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-1101 | 메서드 분할 경로의 405 `Allow` 는 첫 라우트의 메서드만 싣는다(예: `/api/v1/blog/posts` 에 PUT → `Allow: POST`, GET 도 되는데). | LOW | 계획서 L2 — 사용자 결정으로 현행 유지, 값만 기록(산출물 `allow-405.json`). | 2026-10-20 | 클라이언트가 Allow 로 메서드를 고르는 사례가 생기면 405 응답에서 경로의 전체 메서드를 모은다. |
| R-1102 | 로그인 화면 GET 마다 익명 Redis 세션이 생긴다 — 측정: 50회 GET → 키 50개 증가, TTL ≤ 1800초(`ADMIN_SESSION_IDLE_SECONDS`). | LOW | 이전 그룹 R-704 와 같은 항목, 측정만 하라는 계획서 §1.8. 키는 미사용 만료로 사라진다. | 2026-10-20 | 로그인 화면이 공개 인터넷에 열리거나 Redis 메모리 경보가 나면 CSRF 토큰을 서명 쿠키로 옮긴다. |
| R-1103 | JavaScript 가 꺼진 브라우저는 관리 화면 상태 변경이 403 이다(측정: 생성 403). 로그인은 hidden 필드라 된다. | LOW | 설계상 수용(이전 그룹 R-703, 계획서 §1.8). | 2026-10-20 | — |
| R-1104 | primary 장애는 컨테이너 정지가 아니라 `offline_mode` 로 주입한다(tmpfs). 네트워크 단절(응답 없음·hang)은 주입하지 않았다 — 이미 열린 풀 연결에는 읽기 타임아웃이 없다. | MED | ADR-004. 정지(즉시 실패)는 확인했다. | 2026-10-20 | 네트워크 분리 장애를 운영에서 겪으면 `connect_args` 에 read/write timeout 을 두고 `docker compose pause` 로 주입하는 테스트를 더한다. |
| R-1105 | replica 대체는 요청마다 replica 를 먼저 시도한다 — replica 가 오래 죽어 있으면 읽기마다 연결 시도(접속 거부는 즉시, 응답 없음은 `connect_timeout` 10초)가 앞선다. | LOW | ADR-007 — 회로 차단기는 범위 밖(사용자 결정은 "한 번 재시도"). | 2026-10-20 | replica 장애가 길어지는 운영이면 실패한 replica 를 잠시 빼는 상태를 라우터에 둔다. |
| R-1106 | Windows 의 Celery worker 는 `--pool=solo` 이고 `CTRL_BREAK` 로 끝나 종료 로그가 없다. | LOW | Celery 는 Windows prefork 를 지원하지 않는다. Linux(WSL 네이티브 클론)에서 prefork worker 가 `Warm shutdown` 으로 정상 종료하는 것을 확인했다. | 2026-10-20 | — |
| R-1107 | uvicorn 기본 `--proxy-headers` 는 127.0.0.1 피어의 `X-Forwarded-For` 로 `request.client` 를 바꾼다 — 같은 호스트의 프록시 뒤에서 `TRUSTED_PROXY_HOPS=0` 이면 클라이언트 IP 가 XFF 값이 된다. | LOW | e2e 는 `TRUSTED_PROXY_HOPS=1` 로 명시해 영향이 없다. 배포 구성(프록시 위치)의 문제라 이 그룹 범위 밖. | 2026-10-20 | 배포 문서에서 uvicorn `--forwarded-allow-ips`·`TRUSTED_PROXY_HOPS` 를 함께 정하도록 정리할 때. |
| R-1108 | `get_current_user` 가 read-only 세션을 primary 에 고정하므로, 같은 요청에서 같은 read-only 의존성을 쓰는 다른 조회도 primary 로 간다. | LOW | ADR-011 — 지금 이 의존성을 쓰는 라우트는 `/me` 하나다. | 2026-10-21 | `get_current_user` 와 다른 조회를 함께 쓰는 라우트가 생기면 primary 전용 read-only 의존성을 따로 두고 `tests/session_overrides.py` 에 함께 등록한다. |
| R-1109 | 관리 화면(sqladmin 하위 Starlette 앱)의 처리되지 않은 예외는 하위 앱의 `ServerErrorMiddleware` 가 평문 500 을 보낸 뒤 다시 올려, 바깥 앱이 traceback 을 한 번 더(전역 핸들러) 남기고 uvicorn 이 또 남기며 연결을 닫는다. 결정 2(ADR-013)의 미들웨어는 바깥 앱에 있어 이 경로를 바꾸지 못한다(응답이 이미 시작됨). | LOW | 결정 2 의 범위는 API 앱이다. | 2026-10-21 | 관리 화면의 처리되지 않은 예외가 문제가 되면 관리 하위 앱의 미들웨어 목록 맨 앞에 같은 처리를 둔다. |
| R-1110 | 413(Content-Length 초과)은 본문을 읽지 않고 답하므로 서버가 그 연결을 닫는다(남은 본문을 버릴 수 없음). 400(필드 초과)은 본문을 다 읽어 연결이 유지된다. | LOW | ADR-012 — 10 MiB 를 끝까지 읽어 주는 것이 상한의 목적에 어긋난다. | 2026-10-21 | — |
