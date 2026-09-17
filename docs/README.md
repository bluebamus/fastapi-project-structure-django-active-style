# 문서 안내

이 폴더에는 성격이 다른 문서가 섞여 있습니다. **무엇을 하려는지에 따라 볼 곳이 다릅니다.**

## 처음이라면 — 읽는 순서

| 순서 | 문서 | 목적 |
|---|---|---|
| 1 | [`guides/QUICKSTART.md`](guides/QUICKSTART.md) | Redis만 준비해 30초 만에 띄워 보기 |
| 2 | [`../README.md`](../README.md) | 구조 전반, 앱 자동 등록 규약, 계층 규칙 |
| 3 | [`guides/orm-raw-workflow.md`](guides/orm-raw-workflow.md) | **ORM/Raw 중 무엇을 언제 쓰고 어떻게 만드는가** |
| 4 | [`guides/ARCHITECTURE.md`](guides/ARCHITECTURE.md) | 디렉터리별 역할과 파일 단위 책임 |
| 5 | [서버 수명주기 HTML 안내서](guides/server-lifecycle-guide.html) | 설정·등록·lifespan·자원·요청·종료의 실제 클래스·함수 추적 |
| 6 | [신규 뷰·테이블 HTML 개발 안내서](guides/feature-development-guide.html) | MVC·DI·ORM/Raw·트랜잭션·비동기·migration·테스트 개발 지침 |

새 기능을 만들 예정이라면 3번이 핵심입니다. 두 예제 기능
(`app/features/catalog/` = ORM, `app/features/reports/` = Raw)을 함께 열어 두고 읽으세요.

## 폴더별 성격

| 경로 | 성격 | 언제 보나 |
|---|---|---|
| [`guides/`](guides/) | **살아 있는 개발 가이드** | 개발할 때. 현재 코드 기준으로 유지된다 |
| [`guides/QUICKSTART.md`](guides/QUICKSTART.md) · [`guides/ARCHITECTURE.md`](guides/ARCHITECTURE.md) | 살아 있는 문서 | 시작할 때·구조를 확인할 때 |
| [`project-guide/`](project-guide/) | 버전별 시스템 가이드 | 기능별 워크플로를 훑을 때 |
| [`django-style-app-automation-development-spec-2026-08-12/`](django-style-app-automation-development-spec-2026-08-12/) | **설계 기준선 (날짜 고정)** | 앱 자동화의 원 명세를 볼 때 |
| [`specs/orm-raw-repository/`](specs/orm-raw-repository/) | **설계 기준선 (착수 시점 고정)** | ORM/Raw 규칙의 원 명세를 볼 때 |
| [`crp/`](crp/) | **검수 이력 (내부용)** | 어떤 결함이 왜 그렇게 고쳐졌는지 추적할 때 |

### 날짜 이름 폴더는 로컬 작업 기록입니다

정확히 `YYYY-MM-DD` 형식인 폴더는 일시적인 분석·계획 산출물이며 GitHub에 올리지 않습니다.
현재 코드에 적용되는 규칙은 [`guides/`](guides/), 결정 근거는 `crp/`를 봅니다.

### `crp/` 는 검수 추적 기록입니다

작업 그룹별로 결함 대장(ledger)·잔여 위험(residual-risk)·라운드 로그(run-log)를 남깁니다.
개발에 필요한 문서는 아니지만, **"이 코드가 왜 이렇게 생겼는가"** 를 되짚을 때 가장 정확한
기록입니다. 각 결함에는 재현 조건과 회귀 테스트가 연결돼 있습니다.

| 그룹 | 다룬 것 |
|---|---|
| `crp/groups/orm-raw-repository/` | ORM/Raw Base, 예제 기능, 문서·게이트 |
| `crp/groups/runtime-lifecycle/` | 자원 정리, 로깅 큐, Celery 워커 생명주기 |
| `crp/groups/docs-learnability/` | 이 문서 체계 자체 |

## 규칙은 문서가 아니라 테스트가 강제합니다

이 저장소의 규칙 대부분은 **위반하면 `pytest` 가 막습니다.** 문서를 안 읽어도 틀린 코드는
통과하지 못합니다. 문서는 "왜 그런 규칙인가" 를 설명하는 역할입니다.

```bash
python -m scripts.review_gate     # 정적 검사·테스트·공급망·문서 검사를 한 번에
```
