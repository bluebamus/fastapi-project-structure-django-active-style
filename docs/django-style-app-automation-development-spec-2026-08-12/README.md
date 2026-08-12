# Django 스타일 앱 자동화 개발 명세 모음

- 정리일: 2026-08-12
- 대상: `fastapi-project-structure-django-active-style`
- 목적: `fastapi-default-project-structure`를 기반으로 Django 스타일 앱 자동 발견·등록 기능을 적용하기 위한 검토, 설계 및 실행 계획을 한곳에서 제공한다.

## 권장 열람 순서

1. [프로젝트 구조 및 기능 개선 계획](01-project-hardening-plan-2026-08-11.md)
   - 최초 구조 검토, 위험도와 개선 우선순위, 이후 실행 결과를 기록한다.
2. [Django 식 앱 자동 등록 설계와 개발 내역](02-django-style-app-discovery-concept-2026-08-12.md)
   - 프로젝트 목적, Django 대응 범위, 자동 발견·결선 원리와 설계 근거를 설명한다.
3. [Django 스타일 앱 자동화 개발 명세](03-django-style-app-automation-development-spec-2026-08-12.md)
   - 정식 요구사항, 설계, 변경 대상, 개발 단계, 검증, 브랜치·commit·push 계획을 정의한다.

## 문서별 역할

| 순서 | 문서 | 성격 | 주요 내용 |
|---|---|---|---|
| 1 | `01-project-hardening-plan-2026-08-11.md` | 검토·개선 기록 | 초기 문제, 권장 우선순위, 완료·제외·후속 범위 |
| 2 | `02-django-style-app-discovery-concept-2026-08-12.md` | 개념·설계 근거 | Django 대응, registry 원리, 앱 규약, 운영 경계 |
| 3 | `03-django-style-app-automation-development-spec-2026-08-12.md` | 실행 명세 | `FR/CR/NFR/BC/SEC/AC` 요구사항, 설계, 개발·검증·Git 계획 |

## 기준 문서

구조와 실제 사용법의 최종 기준은 저장소 루트 [README](../../README.md)이다. 이 폴더의 문서는 자동 앱 관리 기능을 분석하고 변경을 계획하기 위한 보조 명세이며, 구현 후 실제 동작과 차이가 생기면 코드와 루트 README를 먼저 확인하고 이 문서를 갱신한다.
