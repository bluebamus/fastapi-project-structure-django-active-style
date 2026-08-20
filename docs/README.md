# 문서 안내

이 폴더에는 성격이 다른 문서가 섞여 있습니다. **무엇을 하려는지에 따라 볼 곳이 다릅니다.**

## 처음이라면 — 읽는 순서

| 순서 | 문서 | 목적 |
|---|---|---|
| 1 | [`QUICKSTART.md`](QUICKSTART.md) | 인프라 없이 30초 만에 띄워 보기 |
| 2 | [`../README.md`](../README.md) | 구조 전반, 앱 자동 등록 규약, 계층 규칙 |
| 3 | [`guides/orm-raw-workflow.md`](guides/orm-raw-workflow.md) | **ORM/Raw 중 무엇을 언제 쓰고 어떻게 만드는가** |
| 4 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | 디렉터리별 역할과 파일 단위 책임 |

새 기능을 만들 예정이라면 3번이 핵심입니다. 두 예제 기능
(`app/features/catalog/` = ORM, `app/features/reports/` = Raw)을 함께 열어 두고 읽으세요.

## 폴더별 성격

| 경로 | 성격 | 언제 보나 |
|---|---|---|
| [`guides/`](guides/) | **살아 있는 개발 가이드** | 개발할 때. 현재 코드 기준으로 유지된다 |
| [`QUICKSTART.md`](QUICKSTART.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) | 살아 있는 문서 | 시작할 때·구조를 확인할 때 |
| [`project-guide/`](project-guide/) | 버전별 시스템 가이드 | 기능별 워크플로를 훑을 때 |
| [`concepts/`](concepts/) | 개념 설명 | 자동 발견 registry 의 배경이 궁금할 때 |
| [`orm-raw-repository/`](orm-raw-repository/) | **설계 기준선 (날짜 고정)** | 규칙의 *근거*를 확인할 때 |
| [`django-style-app-automation-development-spec-2026-08-12/`](django-style-app-automation-development-spec-2026-08-12/) | **설계 기준선 (날짜 고정)** | 앱 자동화의 원 명세를 볼 때 |
| [`crp/`](crp/) | **검수 이력 (내부용)** | 어떤 결함이 왜 그렇게 고쳐졌는지 추적할 때 |

### 날짜가 붙은 폴더는 "그때의 기준"입니다

`orm-raw-repository/2026-08-13/` 처럼 날짜가 박힌 폴더는 **작업을 시작할 때 확정한 명세**이고,
이후 코드가 그것을 향해 구현됐습니다. 지금도 규칙의 권위 있는 근거지만, **현재 코드 상태를
설명하는 문서는 아닙니다.** 일상 개발에는 `guides/` 를 보세요.

특히 [`orm-raw-repository/2026-08-13/workflow-guide.md`](orm-raw-repository/2026-08-13/workflow-guide.md)
는 1,200행 규모의 상세 지침서입니다. 코드 예시 전문·보안 규칙·테스트 지침이 필요하면 여기를
보고, "무엇을 언제 쓰나" 는 [`guides/orm-raw-workflow.md`](guides/orm-raw-workflow.md) 가 답합니다.

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
