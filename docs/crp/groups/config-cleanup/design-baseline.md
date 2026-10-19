# Design Baseline — config-cleanup (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)**
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 사유 — 사용자가 세 묶음의 삭제를 정했고 감독자가 명세로 세부를 확정했다.

## 1. 목적 / 배경

`SMTP_*`(`SMTPSettings`)·`UPLOAD_*`(`UploadSettings`)·`SESSION_EXPIRE_SECONDS` 는 정의만 있고 앱 코드가 읽지 않았다.
"설정이 있으니 기능도 있겠지" 라는 오해를 만들고, `SMTP_PASSWORD` 는 쓰지도 않는 값이 배포 검사 대상이었다.
세션 만료 설정은 이미 있다 — `ADMIN_SESSION_MAX_AGE_SECONDS`·`ADMIN_SESSION_IDLE_SECONDS`·`ACCESS_TOKEN_EXPIRE_MINUTES`·
`REFRESH_TOKEN_EXPIRE_DAYS`. 이것들을 정본으로 README 표 하나에 모은다.

**과거 문서의 언급은 이력이다.** `admin-login` residual-risk R-303, `runtime-lifecycle` REQ-013·ADR-010(비밀번호 3종 검사에
`SMTP_PASSWORD` 포함), `docs-learnability` design-baseline 의 SMTP·업로드 언급은 당시 사실의 기록이라 고치지 않는다.
현행 상태는 이 그룹이 정한다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "smtp는 삭제해줘." / `SESSION_EXPIRE_SECONDS` → "삭제, 기존 만료 설정을 정본으로" / `UPLOAD_*` → "삭제". "세션 만료 시간 설정은 있어야 한다." | 세 묶음의 필드·클래스·export·싱글턴·`.env.example`·문서·테스트 참조 전부 삭제. `SESSION_COOKIE_NAME`·`SESSION_SECRET_KEY` 유지. 남은 `.env` 줄은 무시(거부 아님). 세션·토큰 만료를 README 표 하나로. 사용처 없는 설정 재발 방지 계약 테스트. | Active | ADR-001~ADR-003, F-001~F-003 |
| REQ-002 | 2026-10-19 | "API_VERSION 삭제, 로그 설정은 실제로 연결" (R-801 의 남은 5필드) | `API_VERSION` 필드·`ApiSettings`·`.env.example`·문서·테스트 참조 삭제(경로 접두어는 코드 고정 그대로, 남은 키 무시). `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`·`LOG_CONSOLE_ENABLED` 를 로깅 구성에 연결(기본 출력 불변, 콘솔 on/off 는 모든 경로에서 한 곳의 판단, 전부 꺼짐 경고, 잘못된 형식은 설정 오류, 마스킹 유지). 계약 테스트 예외 목록 비움. | Active | ADR-004~ADR-007, F-004·F-005 |
| REQ-003 | 2026-10-19 | "결함은 바로 수정" — R-804(`python main.py` 접속 줄 logging 오류) | 접속 레코드가 오류 없이 요청 라인 형식으로 찍히고 마스킹·시간대·`LOG_DATE_FORMAT` 유지. 형식 통일(R-803)은 건드리지 않음. | Active | ADR-008, F-006·F-007 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | **남은 키는 무시한다(거부하지 않는다).** 모든 설정 클래스가 `extra="ignore"` 라 기존 `.env` 의 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS` 는 조용히 버려진다. 레거시 `ADMIN` 처럼 `validate_renamed_settings` 에 넣지 않는다. README 업그레이드 노트에 "지워도 되고 남아도 무시" 를 적는다. | `ADMIN` 은 남으면 관리 화면이 **켜지는** 보안 반전이었다. 이 키들은 효과 없는 값일 뿐이다. 거부하면 멀쩡한 배포가 업그레이드만으로 멈춘다. | Active | — |
| ADR-002 | 2026-10-19 | **배포 검사에서 `SMTP_PASSWORD` 항목을 뺀다(검사 자체는 유지).** 선택적 비밀번호 루프는 `REDIS_PASSWORD` 하나가 되어 직접 `if` 로 쓴다. 개발 환경 placeholder 거부 테스트의 SMTP 사례는 `REDIS_PASSWORD` 사례로 바꿔 같은 경로를 계속 덮는다. | runtime-lifecycle ADR-010 의 비밀번호 3종 중 SMTP 는 소비 코드가 없어 의미가 없다. MYSQL·REDIS 판정은 그대로. | Active | runtime-lifecycle ADR-010 의 SMTP 부분 |
| ADR-003 | 2026-10-19 | **설정 사용 계약 테스트.** 모든 Settings 필드 이름이 기존 환경변수 검사와 같은 소스(app·scripts·migrations·`main.py`)와 `config.py` 에서 `\.NAME\b` 또는 `getattr(x, "NAME")` 로 나타나야 한다. 예외 목록 `UNUSED_FIELD_EXCEPTIONS`(사유 포함, 낡으면 실패). `config.py` 를 포함하는 이유: `DATABASE_URL` 같은 프로퍼티가 `self.MYSQL_*` 로 읽고 app 은 프로퍼티만 읽는다. | 오탐 0 으로 동작함을 확인(예외 5건은 기존 문서가 이미 "선언만" 이라 적은 필드). 한계는 R-802. | Active | — |

| ADR-004 | 2026-10-19 | **`API_VERSION` 은 클래스째 지운다.** 필드가 하나뿐인 `ApiSettings`·`get_api_settings`·`api_settings` 를 삭제하고 남은 `.env` 줄은 ADR-001 과 같이 무시한다. URL 버전은 각 앱 router 의 `/v1/...` 선언 그대로. | 읽는 코드가 없고 prefix 를 바꾸지도 못했다. 빈 클래스를 남길 이유가 없다. | Active | — |
| ADR-005 | 2026-10-19 | **형식·날짜 연결.** `LOG_CONSOLE_FORMAT` → 앱 root 콘솔 포매터와 `setup_uvicorn_logging()` 의 default 포매터, `LOG_FILE_FORMAT` → app·error 파일 포매터(새 `file` 포매터), `LOG_DATE_FORMAT` → 모든 `TzFormatter` 의 datefmt(uvicorn access 포함, access 의 fmt 는 요청 라인 전용 그대로). 기본값을 기존 하드코딩 형식으로 바꿔 기본 출력 불변. `TzFormatter.formatTime` 은 datefmt 뒤에 with_ms(development) 밀리초를 붙인다 — 예전에는 datefmt 를 주면 밀리초가 빠졌지만 아무도 주지 않았다. `LOG_FORMAT` 상수는 기본값의 별칭으로 남긴다(공개 export). | 사용자 결정 "실제로 연결". 기본값이 같아야 업그레이드만으로 로그 파서가 깨지지 않는다. | Active | — |
| ADR-006 | 2026-10-19 | **콘솔 on/off 는 `console_enabled()` 한 곳에서 판단한다.** `build_dictconfig()`(콘솔 핸들러 생략)·`setup_uvicorn_logging()`(핸들러 없이 `propagate=True` — 파일이 있으면 거기에만 남음)·`adopt_external_handlers()`(uvicorn CLI 기본 핸들러와 Celery 워커 핸들러 중 콘솔(`StreamHandler` 이되 `FileHandler` 아님)을 걷어내고, 핸들러가 다 빠진 로거는 전파, 남은 핸들러에 마스킹)가 모두 이 함수만 본다. 전부 꺼짐(콘솔 false + 파일 없음)은 `configure_logging()` 이 1회 stderr 경고. uvicorn CLI·Celery 핸들러의 **형식**은 바꾸지 않는다(기본 출력 유지 — R-803). | 경로마다 판단하면 한 경로만 꺼지지 않는 사고가 난다. 경고는 logging 이 꺼진 상태라 stderr 에 직접 쓴다. | Active | — |
| ADR-007 | 2026-10-19 | **형식 검증은 샘플 렌더 한 번.** `LogSettings` field_validator 가 `logging.Formatter(fmt, style="{")` 로 `tzname`·`appname`·`classname` 을 채운 샘플 `LogRecord` 를 렌더하고 실패하면 `ValueError`(→ 설정 오류). `TzFormatter` 는 `config` 를 import 하므로 config 안에서 쓰지 못한다 — 그가 채우는 세 필드를 직접 넣어 같은 결과를 낸다. 날짜 형식은 빈 값(공백만)만 막는다. 계약 테스트의 예외 목록은 비었으므로 목록과 설명을 지운다(ADR-003 의 예외 목록 부분 대체). | 명세 §2. strftime 은 대부분을 받아들인다. | Active | ADR-003 의 `UNUSED_FIELD_EXCEPTIONS` 부분 |
| ADR-008 | 2026-10-19 | **접속 줄은 uvicorn `AccessFormatter` 를 재사용하고, 마스킹은 인자 단위로 한다.** `TzAccessFormatter(TzFormatter, AccessFormatter)` — args 를 `client_addr`·`request_line`·`status_code` 로 푸는 일은 uvicorn 이, 시각·시간대·`tzname` 은 `TzFormatter` 가 한다(색 끔). `RedactingFilter` 는 비밀값이 인자 하나 안에 있으면 그 인자만 가려 args 모양을 지키고, 인자만으로 못 가리면(틀과 인자에 걸침) 예전처럼 전개 후 가리고 비운다. | 조사 중 같은 원인의 형제 결함 발견(F-007): args 를 비우면 uvicorn CLI 의 `AccessFormatter` 도 `?token=` 요청마다 logging 오류. 포매터 쪽 방어만으로는 CLI 경로를 못 고친다 — 공유 지점(필터)에서 고친다. | Active | — |

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성(REQ-001).
- v0.2 (2026-10-19): REQ-002, ADR-004~ADR-007.
- v0.3 (2026-10-19): REQ-003, ADR-008.
