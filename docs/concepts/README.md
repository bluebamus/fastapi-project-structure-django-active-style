# docs/concepts — 개념 / 기술 심화 문서

이 폴더는 프로젝트의 **기술적 개념과 패턴을 깊이 있게 설명하는 휴먼 리딩용 문서**를
통합 저장하는 곳입니다. "왜 이렇게 동작하는가", "두 방식 중 무엇을 언제 쓰는가"
같은, 코드만으로는 드러나지 않는 설계 의도와 배경 지식을 다룹니다.

> 구조·배선의 공식 설명은 저장소 루트 [`../../README.md`](../../README.md) 가 단일 소스입니다.
> 이 폴더는 그 위에 얹는 **개념 설명/심화 해설** 담당입니다.

## 문서 작성 규칙

- **파일명:** `<주제-슬러그>-<YYYY-MM-DD>` (생성 날짜를 파일명 뒤에 부착)
- **형식:** `.md` 또는 `.html` 중 내용에 맞는 하나. 도식이 핵심이면 `.html`, 텍스트 중심이면 `.md`
- **도식화:** Mermaid 다이어그램 + ASCII 그림으로 흐름을 시각화
- **서술:** 초심자도 따라올 수 있는 친절하고 자세한 내러티브 설명
- **단일 진실 소스:** 코드와 문서가 다르면 코드가 정답 — 문서를 갱신하거나 문서를 지운다

## 문서 목록

| 문서 | 작성일 | 요약 |
|------|--------|------|
| [django-style-app-discovery](../django-style-app-automation-development-spec-2026-08-12/02-django-style-app-discovery-concept-2026-08-12.md) | 2026-08-12 | **이 프로젝트의 목적과 설계 근거.** Django 앱 규약을 FastAPI 로 가져오며 선언 목록마저 없앤 이유, 발견/결선 분리라는 뼈대, Django 대응표, 그리고 "자동이라서 조용해지는 실패" 를 시끄럽게 만든 개발 내역. |
| [auto-discovery-registry](auto-discovery-registry-2026-06-25.html) (HTML) | 2026-06-25 | 자동발견(`AppConfig`/`AppRegistry`) 설계·흐름 분석 + Mermaid 도식. 이 저장소의 **현행 배선** — `core/registry.py` 의 `AppRegistry.discover()` 가 `pkgutil` 로 `app.features` 직계 하위 패키지를 스캔한다(등록 목록 없음). |
