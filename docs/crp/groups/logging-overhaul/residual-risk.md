# Residual Risk — logging-overhaul (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-901 | 여러 프로세스가 같은 파일을 쓰면(uvicorn `--workers` 2+, Celery prefork 동시성 2+, beat 를 같은 `LOG_DIR` 로) 회전이 안전하지 않다. uvicorn spawn 워커만 WARNING 으로 감지하고 Celery 는 감지하지 않는다. | MED | charter 2-2 비목표, ADR-008. README "여러 워커 = 콘솔 + 수집기/logrotate, 파일 로그 끔" 으로 운영 규칙을 둔다. | 2026-10-19 | 다중 프로세스 파일 로그가 실제로 필요해지면 프로세스별 파일 이름(pid·노드명) 또는 중앙 수집 프로세스를 설계한다. |
| R-902 | Celery 워커가 로깅 신호를 받기 전(import 시점)의 줄 1~2개는 웹 파일 `app.log` 로 간다. | LOW | ADR-001 — import 시점에 종류를 정하면 웹이 그 모듈을 import 할 때 웹 줄이 celery.log 로 간다. 스모크에서 1줄(`[database] 라우팅 구성`) 확인. | 2026-10-19 | 워커 기동 줄이 늘거나 파일 충돌이 관측되면 Celery CLI 진입 신호(예: `user_preload_options`)로 앞당긴다. |
| R-903 | 4글자 이상 비밀값은 부분 문자열 일치로 가린다 — 값이 흔한 단어(예: `MYSQL_USER=root`)면 그 단어가 로그 어디서나 `***` 가 된다. | LOW | ADR-006, 사용자 결정(4글자 미만만 예외). 가리지 않는 쪽의 위험(계정명 노출)이 더 크다. | 2026-10-19 | 진단이 막히는 사례가 나오면 계정명은 단어 경계 일치로 좁힌다. |
| R-904 | `uvicorn main:app --log-level` 은 uvicorn 로거 레벨을 정하므로 `LOG_APP_LEVELS=uvicorn=DEBUG` 는 그 레벨 아래로 내려가지 못한다(올리는 것은 된다). CLI `--log-config` 로 준 핸들러는 걷힌다. | LOW | charter 2-2. CLI 의 레벨 옵션은 사용자가 명시한 값이라 덮어쓰지 않는다. 핸들러는 ADR-004 로 프로젝트가 소유한다. | 2026-10-19 | — |
| R-905 | 보관 삭제와 날짜 교체는 그 파일에 **쓸 때** 일어난다 — 쓰지 않는 프로세스(꺼진 워커)의 오래된 파일은 지워지지 않는다. | LOW | 표준 `TimedRotatingFileHandler` 모델. 별도 청소 스케줄은 범위 밖. | 2026-10-19 | 정지된 노드의 디스크 증가가 문제되면 배포 측 `logrotate`/cron 으로 청소한다. |
| R-906 | 실기동 스모크는 Windows 에서 `--pool=solo` 만 돌렸고 fakeredis 에 Lua 가 없어 `--without-mingle --without-gossip --without-heartbeat` 를 썼다. prefork 자식의 listener 재시작은 단위 테스트로만 확인했다. | LOW | Celery 는 Windows 에서 prefork 를 지원하지 않는다(worker_lifecycle 문서). | 2026-10-19 | Linux CI 나 스테이징에서 prefork 워커로 `celery.log` 에 태스크 줄이 남는지 한 번 확인한다. |
| R-907 | uvicorn 접속 줄 끝의 상태 문구(`200 OK` 의 `OK`)가 없어졌다. | LOW | ADR-004 — 요청 줄은 `getMessage()` 그대로. 전용 포매터는 줄 유실 위험만 남긴다. | 2026-10-19 | — |
