"""Home 기능 패키지.

이 파일은 **가볍게 유지한다**. 라우터·모델을 여기서 import 하지 않는다 — 결선은
``AppRegistry`` 가 컨벤션 경로에서 직접 한다(``tests/core/test_import_boundary.py``).

다만 import-time 초기화 훅 하나는 남는다: access-log sink 등록. 이 등록은
미들웨어 설정보다 **먼저** 끝나 있어야 해서 발견 단계에 붙어 있다. 훅은 빠르고
멱등적이어야 하며 DB·네트워크 I/O 를 하면 안 된다(``app/core/registry.py`` 참고).
"""

from app.features.home.access_log_sink import register_sink

register_sink()
