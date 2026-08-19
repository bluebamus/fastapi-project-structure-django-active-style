"""Home 앱 초기화 훅.

Django 의 `AppConfig.ready()` 자리다. `AppRegistry.install_hooks()` 가 부팅 시
한 번 호출한다.

이 결선이 `__init__.py` 의 import-time 부수효과가 아닌 이유는 **추적 가능성**이다.
import 부작용은 "이 모듈을 import 하면 무슨 일이 일어나는가" 를 코드에서 읽을 수
없게 만든다. 테스트가 home 패키지를 건드리는 것만으로 sink 가 등록되면, 결과가
테스트 실행 순서에 좌우된다.
"""

from app.features.home.access_log_sink import register_sink


def ready() -> None:
    """접속 로그 sink 를 미들웨어에 등록한다.

    **멱등**이다 — `set_access_log_sink()` 가 기존 sink 를 교체하므로 여러 번
    불려도 등록된 sink 는 항상 하나다(재기동·lifespan 재진입 대비).
    """
    register_sink()
