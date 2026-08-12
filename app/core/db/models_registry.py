"""기능 모델 import 지점 — `AppRegistry` 위임 facade.

Alembic autogenerate 와 DEBUG 모드 테이블 생성은 둘 다 `Base.metadata` 가 채워져
있어야 동작한다. 그러려면 각 기능의 models 모듈이 import 되어 있어야 하는데,
같은 import 목록을 여러 파일에 복제하면 새 기능 추가 시 한쪽만 고쳐 조용히
어긋난다. 증상은 나중에 "마이그레이션이 비어 있음" 또는 "테이블이 안 생김" 으로
나타나서 원인을 찾기 어렵다.

**앱 목록의 출처는 `app.core.registry.AppRegistry` 하나뿐이다** (NFR-05).
이 모듈은 자체 디렉터리 스캔을 하지 않고 registry 의 발견 결과를 걸러 쓴다 —
스캔 로직이 둘이 되면 런타임과 Alembic 이 서로 다른 앱 목록을 볼 수 있다.

기존 호출부(`session.py`, 테스트)를 그대로 두기 위해 함수 이름과 반환 형식은
유지한다. 새 코드는 `AppRegistry` 를 직접 쓰는 편이 낫다.
"""

import importlib.util

from app.core.registry import AppModule, AppRegistry

_MODELS_SUFFIX = "models.models"


def _model_module(app_module: AppModule) -> str:
    return f"{app_module.package}.{_MODELS_SUFFIX}"


def _has_models(app_module: AppModule) -> bool:
    """앱이 `models/models.py` 를 가지고 있는가."""
    try:
        return importlib.util.find_spec(_model_module(app_module)) is not None
    except ModuleNotFoundError:
        # models 패키지 자체가 없는 기능 — 정상이다(auth 처럼 모델이 없는 경우).
        return False


def iter_model_modules() -> list[str]:
    """models 를 가진 기능의 모듈 경로를 정렬해 돌려준다.

    목록만 만들 뿐 모델 모듈을 import 하지는 않는다. 다만 발견 단계에서 앱
    패키지는 import 된다(초기화 훅 실행) — 그것이 registry 의 계약이다.
    """
    apps = AppRegistry().discover()
    return sorted(_model_module(a) for a in apps if _has_models(a))


def import_all_models() -> list[str]:
    """모든 기능 모델 모듈을 import 해 `Base.metadata` 를 채운다.

    Returns:
        모델을 가진 모듈 경로 목록(정렬됨). 로깅과 검증에 쓴다.
    """
    registry = AppRegistry()
    apps = registry.discover()
    registry.import_models()
    return sorted(_model_module(a) for a in apps if _has_models(a))
