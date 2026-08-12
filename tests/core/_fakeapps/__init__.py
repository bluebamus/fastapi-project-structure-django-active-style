"""registry 검증용 가짜 앱 모음.

실제 `app/features` 를 건드리지 않고 발견·결선 규약을 검사하기 위한 픽스처다.
`AppRegistry.discover(package="tests.core._fakeapps")` 로 이 패키지를 스캔한다.

구성:
    alpha/     라우터만 있는 앱      (models·admin 없음)
    beta/      모델·Admin 만 있는 앱 (라우터 없음)
    _hidden/   언더스코어로 시작 — 발견에서 제외돼야 한다 (NFR-02)

`INIT_CALLS` 는 앱 패키지 `__init__.py` 가 실행됐음을 기록한다. 초기화 훅이
결정적인 순서로 **한 번만** 실행되는지(FR-05, AC-05) 확인하는 데 쓴다.
"""

INIT_CALLS: list[str] = []
