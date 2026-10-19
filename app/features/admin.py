"""SQLAdmin 조립 지점 — 인터페이스를 만들고, 뷰 등록은 registry 에 맡긴다.

``ModelView`` 정의는 각 기능이 소유한다(``app/features/<name>/admin.py``). 모델과 그
관리 화면이 같은 폴더에 있어야 컬럼이 바뀔 때 함께 눈에 들어오고, 기능을 통째로
복사·삭제할 때 관리 화면이 따라온다.

취합은 **자동 발견**으로 한다:
    ``AppRegistry.install_admin(admin)`` 이 발견된 각 앱의 ``admin.py`` 에서
    ``admin_views`` 를 모아 등록한다. 이 파일에 중앙 목록(``ADMIN_VIEWS``)은 없다 —
    새 기능의 관리 화면을 붙이려고 여기를 고칠 일이 없다는 뜻이다 (FR-04, FR-08).

    과거 이 자리에 명시 import 목록이 있었던 이유는 "관용적 수집" 이 위험해서였다.
    ``getattr(module, "admin_views", [])`` 방식은 ``admin.py`` 가 0바이트 빈 파일이어도
    조용히 건너뛰어, ``/admin`` 은 정상 마운트된 채 등록 뷰만 빠진 상태를 아무도
    눈치채지 못하게 만든다(ADMIN-1). 지금은 registry 가 그 구멍을 막는다 —
    ``admin.py`` 가 **있는데** ``admin_views`` 가 없거나 ``ModelView`` 가 아니면
    ``AppContractError`` 로 기동이 멈춘다(NFR-04). 파일이 아예 없을 때만 건너뛴다.

기능 패키지 ``__init__.py`` 로는 재노출하지 않는다:
    수집은 ``app.features.<name>.admin`` **모듈**에서 직접 한다. 패키지가
    ``admin_views`` 를 재노출하면 registry 가 라우터를 얻으려고 패키지를 import 하는
    것만으로 관리 화면이 딸려 와, ADMIN_DISABLED=true 인데도 sqladmin 과 ModelView 가 전부
    메모리에 올라간다(ADMIN-2, 실측). 그러면 ADMIN_DISABLED=true 는 "라우트만 안 붙임" 이 되고,
    sqladmin 을 선택적 의존성으로 분리할 수도 없다.
    회귀 가드: ``tests/test_admin_wiring.py`` 의 ADMIN_DISABLED=true 미로드 검사.

조립 구조:
    ``main.py`` 는 ADMIN_DISABLED=false 일 때 ``register_admin(app, engine, registry)`` **하나만**
    호출하고, 그 안에서 두 책임으로 나뉜다. 아래 함수들은 SQLAdmin 이나 FastAPI 의
    공식 API 가 아니라 **이 프로젝트 내부의 조립 함수**다.

        register_admin(app, engine, registry)   ← main.py 가 부르는 유일한 진입점
          ├─ create_admin_interface(app, engine)   Admin 생성 + /admin 마운트
          └─ registry.install_admin(admin)         발견된 앱의 admin_views 등록

    나눈 이유는 두 책임이 서로 다른 것을 알아야 하기 때문이다 — 생성 쪽은 앱·엔진·제목을
    알아야 하고, 등록 쪽은 앱 목록만 알면 된다. 나뉘어 있으면 각각 단독으로 검증할 수 있다.

URL 등록:
    ``/admin`` 라우트는 ``create_admin_interface()`` 안에서 ``Admin(app, engine, ...)`` 이
    생성되는 순간 SQLAdmin 이 직접 마운트한다. 별도의 ``include_router()`` 나 URL 패턴
    등록은 필요하지 않다 — 찾아도 안 나오는 이유가 이것이다.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN_DISABLED=false(기본): /admin 마운트, ADMIN_DISABLED=true: /admin 자체가 없음(404) —
    이 모듈·sqladmin·관리 세션 미들웨어·인증 백엔드가 아예 만들어지지 않는다.

인증 (admin-login ADR-002~ADR-005):
    ``/admin`` 은 **활성 슈퍼유저 로그인**이 필요하다. 백엔드는
    ``app/features/auth/admin_auth.py`` 의 ``AdminAuthBackend`` 이고, 이 파일의
    ``create_admin_interface()`` 가 ``Admin(..., authentication_backend=...)`` 로 주입한다.
    첫 계정은 ``scripts/create_superuser.py`` 로 만든다. 세션 쿠키(``admin_session``,
    ``Path=/admin``)는 ``SESSION_SECRET_KEY`` 로 서명한다. 로그인 화면은
    ``app/templates/admin/sqladmin/login.html``(Bootstrap)이 sqladmin 기본 화면을 덮어쓴다.

보안 주의 (이 저장소 고유):
    ``User`` 는 자격증명(``hashed_password``)을 보유한다. sqladmin 은
    ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세·수정 폼에
    **모델의 모든 컬럼**을 넣으므로, ``app/features/user/admin.py`` 의 제외 설정을
    지우면 bcrypt 해시가 관리 화면·내보내기에 노출된다 — 지우지 말 것.
    구조 증거: ``tests/core/test_admin_views.py``.
"""

from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db.session import background_db_session
from app.core.registry import AppRegistry
from app.core.security.dependencies import get_password_hasher
from app.core.security.rate_limiter import RateLimiter
from app.features.auth.admin_auth import AdminAuthBackend
from app.features.auth.dependencies.auth_dependencies import get_client_ip_resolver
from config import app_settings, session_settings

# sqladmin 은 templates_dir 의 FileSystemLoader 를 패키지 템플릿보다 먼저 찾는다 —
# 여기의 sqladmin/login.html 이 기본 로그인 화면을 덮어쓴다.
ADMIN_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "admin"


def build_admin_auth_backend(app: FastAPI) -> AdminAuthBackend:
    """운영 협력 객체로 ``AdminAuthBackend`` 를 조립한다.

    Redis 는 lifespan 이 ``app.state.redis`` 에 두므로 로그인 시점에 꺼낸다. sqladmin 은
    하위 앱으로 마운트돼 ``request.app`` 이 이 ``app`` 이 아니라서 ``get_redis(request)`` 를
    쓸 수 없다.
    """
    return AdminAuthBackend(
        session_factory=background_db_session,
        hasher=get_password_hasher(),
        rate_limiter=lambda: RateLimiter(app.state.redis),
        ip_resolver=get_client_ip_resolver(),
        secret_key=session_settings.SESSION_SECRET_KEY,
        https_only=app_settings.ENV in ("staging", "production"),
    )


def create_admin_interface(
    app: FastAPI,
    engine: AsyncEngine,
    authentication_backend: AdminAuthBackend | None = None,
) -> Admin:
    """SQLAdmin 인터페이스를 만들고 FastAPI 앱에 마운트한다.

    **뷰는 등록하지 않는다** — 그것은 ``registry.install_admin()`` 의 몫이다.
    여기서 ``Admin(...)`` 을 생성하는 순간 SQLAdmin 이 ``/admin`` 라우트를 붙인다.

    인증 백엔드는 ``Admin`` 생성 인자라서 뷰 등록 쪽이 아니라 **여기서** 주입한다.

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.
        authentication_backend: 테스트가 협력 객체를 바꿔 넣을 때만 준다. 없으면
            ``build_admin_auth_backend(app)`` 로 운영 구성을 만든다.

    Returns:
        뷰가 아직 등록되지 않은 ``Admin`` 인스턴스.
    """
    backend = authentication_backend or build_admin_auth_backend(app)
    admin = Admin(
        app,
        engine,
        title=f"{app_settings.PROJECT_NAME} Admin",
        authentication_backend=backend,
        templates_dir=str(ADMIN_TEMPLATES_DIR),
    )
    # 로그인 실패·한도 초과 화면을 같은 템플릿 엔진으로 그리도록 넘긴다.
    backend.templates = admin.templates
    # 로그인 템플릿이 `{{ csrf_token(request) }}` 로 세션 토큰을 싣는다(sqladmin 의 GET 로그인
    # 경로는 컨텍스트를 받지 않아 전역 함수로 준다).
    admin.templates.env.globals["csrf_token"] = backend.csrf_token
    return admin


def register_admin(app: FastAPI, engine: AsyncEngine, registry: AppRegistry) -> Admin:
    """관리자 인터페이스를 만들고 발견된 앱의 ModelView 를 등록한다.

    **애플리케이션 조립부(`main.py`)가 호출하는 유일한 진입점.**

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.
        registry: 이미 ``discover()`` 를 마친 레지스트리. 여기서 다시 발견하지
            않는다 — 라우터·모델과 **같은 앱 목록**을 써야 관리 화면만 다른
            집합을 보는 일이 생기지 않는다 (NFR-05).

    Returns:
        구성된 ``Admin`` 인스턴스(테스트에서 등록 뷰를 검사할 수 있도록 반환).
    """
    admin = create_admin_interface(app, engine)
    registry.install_admin(admin)
    return admin
