"""Home 기능 패키지.

이 파일은 **가볍게 유지한다**. 라우터·모델을 여기서 import 하지 않는다 — 결선은
``AppRegistry`` 가 컨벤션 경로에서 직접 한다(``tests/core/test_import_boundary.py``).

import-time 부수효과도 두지 않는다. 부팅 시 한 번 해야 하는 결선(access-log sink
등록)은 ``apps.py`` 의 ``ready()`` 로 옮겼고, ``AppRegistry.install_hooks()`` 가
명시적으로 호출한다. import 만으로 상태가 바뀌면 테스트 결과가 실행 순서에
좌우된다(design-baseline ADR-006).
"""
