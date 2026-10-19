# Ledger — config-cleanup (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope** / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | LOW | REQ-001 | INV-1 | Fix | **Fixed** | Round 1 | `SMTPSettings`(필드 8·TLS/SSL validator)·`get_smtp_settings`·`smtp_settings` 와 `.env.example` SMTP 절이 읽는 코드 없이 남아 있었고, `SMTP_PASSWORD` 가 배포 검사 대상이었다. **조치:** 클래스째 삭제, 배포 검사 항목·관련 테스트 삭제(ADR-002). |
| F-002 | LOW | REQ-001 | INV-1 | Fix | **Fixed** | Round 1 | `UploadSettings`(필드 7)·`get_upload_settings`·`upload_settings` 와 `.env.example` 업로드 절이 읽는 코드 없이 남아 있었다. **조치:** 클래스째 삭제. `python-multipart` 는 유지(로그인 폼 파싱). |
| F-003 | LOW | REQ-001 | INV-1·INV-4 | Fix | **Fixed** | Round 1 | `SESSION_EXPIRE_SECONDS` 가 읽는 코드 없이 남아 "세션 만료 설정" 으로 오해됐다. **조치:** 필드·`.env.example` 줄 삭제, README 세션·토큰 만료 표를 정본으로(ADR-001). |
| F-004 | LOW | REQ-002 | INV-1 | Fix | **Fixed** | Round 2 | `API_VERSION`(`ApiSettings`) 이 읽는 코드 없이 남아 URL 버전을 정하는 설정처럼 보였다. **조치:** 클래스째 삭제, 남은 키 무시(ADR-004). |
| F-005 | LOW | REQ-002 | INV-1·INV-5·INV-6 | Fix | **Fixed** | Round 2 | `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 을 로깅 구성이 읽지 않았고 형식 기본값도 실제 형식과 달랐다. **조치:** 연결(ADR-005·ADR-006), 검증(ADR-007), 기본값 = 기존 형식. |
