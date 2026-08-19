"""앱 자동발견 레지스트리 (컨벤션 기반).

기능 앱은 별도 선언(`INSTALLED_APPS` 같은 중앙 목록)이 없다. 디렉터리 구조와
네이밍 컨벤션만으로 라우터·모델·Admin 을 발견·연결한다.

컨벤션 (app/features/<name>/):
    __init__.py             →  앱 패키지. import-time 초기화 훅 (선택)
    api/routers/router.py   →  <name>_router: APIRouter   (있으면 prefix /api 에 마운트)
    models/                 →  import 시 Base.metadata 에 테이블 등록 (선택)
    admin.py                →  admin_views: list[type]      (선택, SQLAdmin ModelView)

설계의 뼈대는 **발견과 결선의 분리**다. `discover()` 는 "어떤 앱이 있는가" 만
확정하고, `install_routers()` / `import_models()` / `install_admin()` 은 "그 목록을
어떻게 엮는가" 만 담당한다. 덕분에 런타임(main.py)·Alembic(migrations/env.py)·
테스트가 같은 목록을 재사용하며, 앱 목록의 출처가 바뀌어도(수동 목록 방식 등)
결선 코드는 그대로다.

오류 정책 — "파일 부재는 선택, 잘못된 계약은 오류":
    자동 등록은 편의를 주는 대신 실패를 조용하게 만든다. 라우터가 안 붙어도
    서버는 정상 기동하고 해당 기능만 사라지기 때문이다. 그래서 이 모듈은
    **없는 것과 틀린 것을 구분**한다.

        선택 모듈이 아예 없다        → 정상. 건너뛴다.
        모듈 내부의 import 가 틀렸다 → 원래 예외를 그대로 올린다.
        모듈은 있는데 export 가 틀렸다 → AppContractError 로 기동을 멈춘다.

    가운데·아래 두 경우를 "선택 기능 없음" 으로 처리하면 오타 하나가 기능
    하나를 소리 없이 지운다.

Note:
    Django `AppConfig.ready()` 와 역할은 비슷하지만 생명주기는 다르다. 여기서
    초기화 훅은 그냥 파이썬 패키지 import 이며, 프레임워크가 보장하는 준비 단계가
    아니다. 그래서 훅은 빠르고 멱등적이어야 하고 DB·네트워크 I/O 를 하면 안 된다.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from app.utils.logs import get_logger

if TYPE_CHECKING:  # pragma: no cover - 타입 검사 전용
    from fastapi import FastAPI

logger = get_logger("registry")

FEATURES_PACKAGE = "app.features"


class AppContractError(RuntimeError):
    """앱이 registry 규약을 어겼다.

    "선택 구성요소가 없음" 과 구분하기 위한 전용 예외다. 이 예외가 나면 앱을
    건너뛰지 않고 기동을 멈춘다 — 조용히 빠진 기능을 나중에 발견하는 것보다
    지금 터지는 편이 훨씬 싸다.
    """


@dataclass(frozen=True)
class AppModule:
    """발견된 기능 앱 하나. 이름·패키지 경로만으로 구성요소를 컨벤션으로 찾는다.

    Attributes:
        name: 앱 이름 (예: "home"). 라우터 변수명 컨벤션의 기준.
        package: 앱 패키지 dotted 경로 (예: "app.features.home").
        prefix: 라우터 마운트 prefix.
    """

    name: str
    package: str
    prefix: str = "/api"

    @property
    def router_attr(self) -> str:
        """컨벤션 라우터 변수명 (예: home → home_router)."""
        return f"{self.name}_router"

    @staticmethod
    def _import_optional(dotted: str) -> ModuleType | None:
        """선택 모듈을 import 한다. **그 모듈 자체가 없을 때만** None 을 돌려준다.

        `ModuleNotFoundError` 하나로 "파일 없음" 을 판정하면, 파일은 있고 그
        **안의 import 한 줄이 틀린** 경우까지 같은 예외로 잡혀 조용히 삼켜진다.
        그러면 오타 하나에 서버는 에러 없이 뜨고 해당 기능의 라우터·Admin·
        테이블만 사라진다 — 원인 추적이 매우 어렵다.

        그래서 "없다고 하는 모듈(`exc.name`)이 내가 찾던 바로 그 모듈인가" 를
        따진다. 다른 모듈 때문이면 숨기지 않고 원래 예외를 그대로 올린다.
        `exc.name` 이 `dotted` 의 상위 패키지인 경우도 부재로 본다
        (`a.b.c` 를 찾는데 `a.b` 가 없으면 `c` 도 없는 것).
        """
        try:
            return importlib.import_module(dotted)
        except ModuleNotFoundError as exc:
            missing = exc.name
            if missing and (dotted == missing or dotted.startswith(f"{missing}.")):
                return None  # 선택 모듈 자체가 없다 — 정상, 건너뛴다
            raise  # 모듈 내부의 import 실패 — 숨기지 않는다

    def install_hook(self) -> bool:
        """`<package>.apps` 의 `ready()` 를 호출한다(있으면).

        Django 의 `AppConfig.ready()` 자리다. 앱이 부팅 시 한 번 해야 하는 결선
        (예: home 의 access-log sink 등록)을 **명시적인 함수**에 둔다.

        `__init__.py` 의 import-time 부수효과를 쓰지 않는 이유는 추적 가능성이다.
        import 부작용은 "이 모듈을 import 하면 무슨 일이 일어나는가" 를 코드에서
        읽을 수 없게 만들고, 테스트가 모듈을 건드리는 것만으로 상태가 바뀌어
        결과가 실행 순서에 좌우된다.

        `ready()` 는 **멱등**이어야 한다 — 재기동·재진입에서 다시 불릴 수 있다.

        Returns:
            훅을 실제로 호출했으면 True, 모듈이나 `ready` 가 없으면 False.
        """
        module = self._import_optional(f"{self.package}.apps")
        if module is None:
            return False
        ready = getattr(module, "ready", None)
        if ready is None:
            return False
        ready()
        return True

    def load_router(self) -> APIRouter | None:
        """`<package>.api.routers.router` 의 `<name>_router` 를 반환한다.

        라우터 모듈이 없으면 None(라우터 없는 앱 — 정상). 모듈은 있는데
        `<name>_router` 가 없거나 `APIRouter` 가 아니면 `AppContractError`.

        Raises:
            AppContractError: 라우터 모듈은 있으나 규약 export 가 없거나 타입이 틀림.
        """
        module = self._import_optional(f"{self.package}.api.routers.router")
        if module is None:
            return None

        router = getattr(module, self.router_attr, None)
        if router is None:
            raise AppContractError(
                f"앱 '{self.name}' 의 {module.__name__} 에 '{self.router_attr}' 가 없습니다. "
                f"라우터 모듈이 있으면 '{self.router_attr}: APIRouter' 를 정의해야 합니다 "
                "(모듈 자체가 없으면 라우터 없는 앱으로 정상 처리됩니다)."
            )
        if not isinstance(router, APIRouter):
            raise AppContractError(
                f"앱 '{self.name}' 의 '{self.router_attr}' 가 APIRouter 가 아닙니다 "
                f"(실제 타입: {type(router).__name__})."
            )
        return router

    def load_admin_views(self) -> list[type]:
        """`<package>.admin` 의 모듈 레벨 `admin_views` 를 반환한다.

        admin 모듈이 없으면 `[]`(Admin 없는 앱 — 정상). 모듈은 있는데
        `admin_views` 가 없거나 list 가 아니거나 항목이 SQLAdmin `ModelView`
        서브클래스가 아니면 `AppContractError`.

        `sqladmin` 은 이 함수 안에서만 import 한다 — 모듈 레벨에서 끌어오면
        `ADMIN=false` 에서도 sqladmin 이 메모리에 올라간다(SEC-01). 이 함수는
        `install_admin()` 에서만 호출되고, 그 시점엔 이미 ADMIN=true 다.

        Raises:
            AppContractError: admin 모듈은 있으나 `admin_views` 규약 위반.
        """
        module = self._import_optional(f"{self.package}.admin")
        if module is None:
            return []

        from sqladmin import ModelView

        views = getattr(module, "admin_views", None)
        if views is None:
            raise AppContractError(
                f"앱 '{self.name}' 의 {module.__name__} 에 'admin_views' 가 없습니다. "
                "admin 모듈이 있으면 'admin_views: list[type]' 를 정의해야 합니다 "
                "(모듈 자체가 없으면 Admin 없는 앱으로 정상 처리됩니다)."
            )
        if not isinstance(views, list):
            raise AppContractError(
                f"앱 '{self.name}' 의 'admin_views' 가 list 가 아닙니다 "
                f"(실제 타입: {type(views).__name__})."
            )
        for view in views:
            if not (isinstance(view, type) and issubclass(view, ModelView)):
                raise AppContractError(
                    f"앱 '{self.name}' 의 'admin_views' 항목 {view!r} 가 "
                    "sqladmin.ModelView 서브클래스가 아닙니다."
                )
        return list(views)

    def import_models(self) -> None:
        """모델 모듈을 import 하여 테이블을 `Base.metadata` 에 등록한다(있으면).

        패키지(`<package>.models`)와 관례 모듈(`<package>.models.models`)을 **둘 다**
        시도한다. 예전에는 패키지만 import 했는데, 그러면 등록이 각 앱
        `models/__init__.py` 의 재export 한 줄에 걸린다 — 그 줄을 빼먹은 앱(특히
        scaffold 로 만든 앱)은 테이블이 조용히 등록되지 않고, 증상은 한참 뒤에
        "마이그레이션이 비어 있음" 이나 "테이블이 안 생김" 으로만 나타난다.
        `models_registry.iter_model_modules()` 가 이미 관례 모듈 경로를 기준으로
        목록을 만들고 있어, 둘을 맞춰 두면 runtime 과 Alembic 이 같은 집합을 본다.

        이미 import 된 모듈은 `sys.modules` 에서 돌아오므로 두 번 시도해도 부작용은 없다.
        """
        self._import_optional(f"{self.package}.models")
        self._import_optional(f"{self.package}.models.models")


class AppRegistry:
    """기능 앱 자동발견 레지스트리 — 앱 목록의 단일 출처(SSOT).

    사용 순서는 항상 `discover()` → `import_models()` / `install_routers()` /
    `install_admin()` 이다. 결선 메서드는 마지막 `discover()` 결과만 사용하며
    스스로 다시 스캔하지 않는다(두 번째 스캔 로직을 두면 런타임과 Alembic 의
    목록이 어긋날 수 있다).
    """

    def __init__(self) -> None:
        self._apps: list[AppModule] = []

    @property
    def enabled_apps(self) -> list[AppModule]:
        """마지막 `discover()` 결과."""
        return self._apps

    def discover(self, package: str = FEATURES_PACKAGE) -> list[AppModule]:
        """`package` 직계 하위의 기능 앱을 발견한다(컨벤션 스캔).

        앱 = `package` 바로 아래의 서브패키지 중 언더스코어로 시작하지 않는 것.
        발견 목록은 **앱 이름 알파벳순**으로 고정한다 — `pkgutil` 이 돌려주는
        순서는 파일시스템에 따라 달라져서, 정렬하지 않으면 라우트 등록 순서가
        기계마다 달라진다.

        **이 메서드는 부작용이 없다.** 앱이 무엇인지 알아내기만 하고 아무것도
        초기화하지 않는다(C-5). 초기화가 필요하면 `install_hooks()` 를 따로 부른다 —
        "무엇을 import 하면 무엇이 일어나는가" 를 추적할 수 있어야 하기 때문이다.
        이전에는 여기서 각 패키지를 import 해 `__init__.py` 의 import-time 부수효과를
        실행했는데, 그러면 테스트가 모듈을 import 하는 것만으로 sink 가 등록되어
        결과가 테스트 순서에 좌우됐다.

        Returns:
            발견된 `AppModule` 목록(이름 오름차순).
        """
        root = importlib.import_module(package)
        names = sorted(
            info.name
            for info in pkgutil.iter_modules(root.__path__)
            if info.ispkg and not info.name.startswith("_")
        )

        apps = [AppModule(name=name, package=f"{package}.{name}") for name in names]

        self._apps = apps
        logger.debug("discovered %d apps: %s", len(apps), names)
        return self._apps

    def install_hooks(self) -> int:
        """발견된 각 앱의 `apps.ready()` 를 발견 순서대로 호출한다.

        `discover()` 와 분리한 이유는 C-5(발견 단계 부작용 0)다. 초기화는
        **부르는 쪽이 명시적으로** 요청해야 한다.

        Returns:
            실제로 호출한 훅 개수.
        """
        count = sum(1 for module in self._apps if module.install_hook())
        logger.debug("installed %d app hooks", count)
        return count

    def install_routers(self, app: FastAPI) -> int:
        """발견된 각 앱의 `<name>_router` 를 FastAPI 앱에 마운트한다.

        Returns:
            마운트한 라우터 개수.

        Raises:
            AppContractError: 라우터 규약 위반 또는 같은 라우터 객체의 중복 등록.
        """
        seen: dict[int, str] = {}
        count = 0
        for module in self._apps:
            router = module.load_router()
            if router is None:
                logger.debug("앱 '%s' 에 라우터 모듈이 없어 건너뜀", module.name)
                continue
            owner = seen.get(id(router))
            if owner is not None:
                raise AppContractError(
                    f"앱 '{module.name}' 과 '{owner}' 가 같은 APIRouter 객체를 공유합니다 — "
                    "라우트가 중복 등록됩니다."
                )
            seen[id(router)] = module.name
            app.include_router(router, prefix=module.prefix)
            count += 1
        logger.debug("installed %d routers", count)
        return count

    def import_models(self) -> None:
        """발견된 각 앱의 models 패키지를 import 한다(`Base.metadata` 등록)."""
        for module in self._apps:
            module.import_models()

    def install_admin(self, admin: Any) -> int:
        """발견된 각 앱의 `admin.py` 의 `admin_views` 를 SQLAdmin 에 등록한다.

        `admin` 은 `sqladmin.Admin` 인스턴스지만, 이 모듈이 sqladmin 을 모듈
        레벨에서 import 하지 않기 위해(SEC-01) 타입을 좁히지 않는다.

        Returns:
            등록한 view 개수.

        Raises:
            AppContractError: `admin_views` 규약 위반 또는 같은 view 클래스의 중복 등록.
        """
        seen: dict[type, str] = {}
        count = 0
        for module in self._apps:
            for view in module.load_admin_views():
                owner = seen.get(view)
                if owner is not None:
                    raise AppContractError(
                        f"ModelView {view.__name__} 가 앱 '{owner}' 와 '{module.name}' 에 "
                        "중복 등록됐습니다."
                    )
                seen[view] = module.name
                admin.add_view(view)
                count += 1
        logger.debug("installed %d admin views", count)
        return count
