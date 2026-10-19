# Design Baseline — logging-overhaul (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)**
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 사유 — 사용자가 포맷·회전·비밀값·파일 분할을 결정했고 감독자가 명세(L1~L9)로 세부를 확정했다.

## 1. 목적 / 배경

로그를 Django `LOGGING` 처럼 한 곳에서 세부까지 설정하고, 앱·Celery 를 헤더로 구분하되 형식은 하나로, 모든 줄에 모듈·클래스·함수·
시간을 싣고, 레벨을 `.env` 로 제어하고, 파일을 날짜·크기로 회전·분할하며 보관 기간을 두고, DB 계정·비밀번호 같은 비밀값이 로그에 나오지
않게 한다.

조사(base `ede6e1c`)에서 드러난 현재 흐름: 앱 root 만 프로젝트 형식이었고 `uvicorn main:app`·Celery 는 각자 기본 형식(R-803),
`python main.py` 의 접속 줄은 전용 형식, 파일 이름의 날짜는 기동 시각에 고정(날짜 교체 없음), Celery 워커는 root 를 가로채
queue 핸들러가 사라져 파일 로그가 없었고, DSN 정규식은 사용자명을 남기고 `redis://:pw@` 꼴은 아예 놓쳤다.

## 2. 요구사항 레지스터 (append-only)

| ID | 날짜 | 요구 | 출처 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-19 | 명세 L1~L9 — 포맷 통일(C: 모든 경로 항상 프로젝트 형식), 헤더 보강, 필수 필드, `LOG_APP_LEVELS`, 프로세스별+에러 파일, 날짜+크기 회전과 보관 일수, DSN id·비밀번호와 `.env` 비밀값 원문 마스킹, 문서 | 사용자 결정(2026-10-19) + 감독자 명세 | **Active** |

## 3. 설계 결정 (ADR, append-only)

| ID | 날짜 | 결정 | 근거 |
|---|---|---|---|
| ADR-001 | 2026-10-19 | **에러 파일도 프로세스별로 나눈다** — 웹 `error.log`, Celery `celery-error.log`. 이름 표는 `logs/config.py` 의 `LOG_FILES` 하나, 종류는 `_process`(기본 `app`)를 Celery `after_setup_logger` 수신자가 `celery` 로 바꾼다. | 웹·워커가 한 `error.log` 를 함께 쓰면 두 프로세스가 같은 파일을 회전시킨다(Windows 에서는 열린 파일 rename 실패, Linux 에서는 한쪽이 옛 inode 에 계속 씀). import 시점(`app.celery.app`)에 정하지 않은 이유: 웹이 나중에 `.delay()` 를 부르려고 그 모듈을 import 하면 웹 줄이 celery.log 로 간다. 대가는 워커 import 시점 줄(1줄 남짓)이 `app.log` 로 가는 것(R-902). |
| ADR-002 | 2026-10-19 | **회전은 UTC 자정.** `DailyRotatingFileHandler(TimedRotatingFileHandler)` `when="midnight", utc=True`. 크기 초과 분할은 그날 이름의 다음 빈 번호(`app.log.D`, `.1`, `.2`…). | 파일 로그는 staging/production 에만 있고 그 줄의 시각은 UTC(운영 UTC 정책, `TzFormatter use_utc`) — 파일 이름의 날짜와 줄의 날짜가 같아진다. `TIME_ZONE` 기준으로 돌리면 파일 하나에 두 UTC 날짜가 섞인다. 분할 번호를 "다음 빈 번호" 로 하면 자정 교체와 크기 분할이 한 절차가 되고 같은 이름 덮어쓰기가 없다. |
| ADR-003 | 2026-10-19 | **`LOG_BACKUP_COUNT` 를 `LOG_RETENTION_DAYS`(기본 30, 0=삭제 안 함, 음수 오류)로 대체**하고 `LOG_APP_FILENAME`·`LOG_ERROR_FILENAME` 을 삭제한다(남은 키는 `extra="ignore"` 로 무시). | 날짜+크기 분할에서 "개수" 는 하루 분할 수에 따라 보관 기간이 들쭉날쭉해진다. 보관은 기간으로 말하는 것이 운영 요구와 맞다. 두 설정이 공존하면 어느 쪽이 지우는지 모호하다. 파일 이름은 프로세스 종류가 정하므로(ADR-001) 이름 패턴 설정은 의미가 없다. |
| ADR-004 | 2026-10-19 | **모든 경로가 root 의 핸들러 한 벌을 쓴다.** `python main.py` 는 `log_config=None`, uvicorn CLI 가 먼저 붙인 핸들러와 `celery.task` 핸들러는 걷고 root 로 전파(`adopt_external_handlers`), Celery root 는 `configure_logging(force=True, logfile=…)` 로 다시 구성(`--logfile` 은 `WatchedFileHandler` + 파일 형식). `setup_uvicorn_logging()`·`TzAccessFormatter`·`redact_handlers()` 를 삭제한다. | 명세 L1 은 `TzAccessFormatter` 하나를 두라고 했으나, 접속 레코드의 `getMessage()` 가 이미 요청 줄(`client - "GET /p HTTP/1.1" 200`)이라 프로젝트 형식의 `{message}` 로 충분하다. `AccessFormatter` 는 args 5개를 푸는 단계에서 마스킹이 args 를 비우면 줄을 잃는 위험(R-804·F-007)만 남긴다 — 포매터를 지우면 그 실패 모드 자체가 없어진다. 핸들러를 경로마다 만들면 형식·마스킹·앱별 레벨·파일을 경로마다 맞춰야 한다. 잃는 것: 접속 줄 끝의 상태 문구(`OK`). |
| ADR-005 | 2026-10-19 | **헤더별 레벨은 `loggers` 키가 아니라 헤더 이름 필터**(`AppLevelFilter`)다. root 레벨은 `LOG_LEVEL` 과 헤더별 레벨의 최솟값. | 헤더가 경로·로거 이름 표에서 나오므로(INV-2) 기능을 추가해도 손댈 곳이 없다는 성질을 지킨다. 필터 하나가 모든 핸들러(콘솔·큐·`--logfile`)에 같은 규칙을 준다. 큐 앞에서 걸러 버릴 레코드가 큐 자리를 차지하지 않는다. |
| ADR-006 | 2026-10-19 | **비밀값 원문 목록은 `config.LOG_SECRET_SETTINGS` 한 곳**, `configure_logging()` 이 `filters.set_secret_values(log_secret_values())` 로 설치. 4글자 이상은 원문(부분 문자열) 일치, 미만은 `user=`·`username=` 꼴과 DSN 에서만. | 필터 모듈이 config 를 import 하지 않게(로깅이 config 보다 먼저 설 수 있음) 값을 주입한다. 짧은 값(예: `sa`)을 원문 일치로 가리면 일반 단어가 지워져 로그를 못 쓴다. 계약 테스트가 이름 규칙의 새 설정을 목록에 넣게 강제한다. |
| ADR-007 | 2026-10-19 | **prefork 자식의 파일 listener 는 `worker_process_init` 에서 다시 세운다**(같은 큐·핸들러). listener 를 시작한 pid 와 같으면(solo 풀) 아무것도 하지 않는다. | fork 는 스레드를 복제하지 않아 자식 레코드가 아무도 비우지 않는 큐에 갇혀 상한에서 버려진다. solo 풀도 같은 신호를 같은 프로세스에서 보낸다(스모크에서 발견, F-009) — 살아 있는 listener 옆에 둘째를 세우면 같은 파일 핸들러를 두 스레드가 쓰고 첫째는 멈출 수단이 없다. |
| ADR-008 | 2026-10-19 | **다중 프로세스 감지는 uvicorn 만 한다** — 파일 로그가 켜진 채 `multiprocessing.parent_process()` 가 있으면(uvicorn `--workers` 2+ 는 spawn) WARNING 한 줄. Celery prefork·beat 는 문서만. | billiard(prefork) 자식은 `multiprocessing.parent_process()` 로 잡히지 않고, 동시성 값은 로깅 신호에 실려 오지 않는다. 확실하지 않은 감지는 넣지 않는다(명세 L6). |

## 4. 버전
- v0.1 (2026-10-19): 최초 — REQ-001, ADR-001~ADR-008.
