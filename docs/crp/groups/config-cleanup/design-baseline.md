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

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | **남은 키는 무시한다(거부하지 않는다).** 모든 설정 클래스가 `extra="ignore"` 라 기존 `.env` 의 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS` 는 조용히 버려진다. 레거시 `ADMIN` 처럼 `validate_renamed_settings` 에 넣지 않는다. README 업그레이드 노트에 "지워도 되고 남아도 무시" 를 적는다. | `ADMIN` 은 남으면 관리 화면이 **켜지는** 보안 반전이었다. 이 키들은 효과 없는 값일 뿐이다. 거부하면 멀쩡한 배포가 업그레이드만으로 멈춘다. | Active | — |
| ADR-002 | 2026-10-19 | **배포 검사에서 `SMTP_PASSWORD` 항목을 뺀다(검사 자체는 유지).** 선택적 비밀번호 루프는 `REDIS_PASSWORD` 하나가 되어 직접 `if` 로 쓴다. 개발 환경 placeholder 거부 테스트의 SMTP 사례는 `REDIS_PASSWORD` 사례로 바꿔 같은 경로를 계속 덮는다. | runtime-lifecycle ADR-010 의 비밀번호 3종 중 SMTP 는 소비 코드가 없어 의미가 없다. MYSQL·REDIS 판정은 그대로. | Active | runtime-lifecycle ADR-010 의 SMTP 부분 |
| ADR-003 | 2026-10-19 | **설정 사용 계약 테스트.** 모든 Settings 필드 이름이 기존 환경변수 검사와 같은 소스(app·scripts·migrations·`main.py`)와 `config.py` 에서 `\.NAME\b` 또는 `getattr(x, "NAME")` 로 나타나야 한다. 예외 목록 `UNUSED_FIELD_EXCEPTIONS`(사유 포함, 낡으면 실패). `config.py` 를 포함하는 이유: `DATABASE_URL` 같은 프로퍼티가 `self.MYSQL_*` 로 읽고 app 은 프로퍼티만 읽는다. | 오탐 0 으로 동작함을 확인(예외 5건은 기존 문서가 이미 "선언만" 이라 적은 필드). 한계는 R-802. | Active | — |

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성(REQ-001).
