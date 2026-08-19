"""
scripts/new_app.py — FastAPI app scaffolding generator (컨벤션 기반, gen-2).

Django-style ``startapp`` equivalent. 앱은 별도 선언(config.py) 없이 디렉터리
구조와 네이밍 컨벤션만으로 AppRegistry 에 자동 발견된다.

컨벤션 (생성되는 구조):
    app/features/<name>/
        api/routers/router.py   →  <name>_router: APIRouter   (/api 에 자동 마운트)
        api/routers/v1/         →  버전별 서브라우터 위치
        models/                 →  ORM 모델 (Base.metadata 자동 등록)
        schemas/ services/ repositories/ dependencies/ tests/
        admin.py (선택)         →  admin_views: list[type]

Usage (CLI):
    python -m scripts.new_app <name> [--with-admin]

Usage (API):
    from pathlib import Path
    from scripts.new_app import scaffold
    scaffold("orders", root=Path.cwd())
"""

from __future__ import annotations

import argparse
import keyword
import pathlib
import sys

# ---------------------------------------------------------------------------
# Template constants
# ---------------------------------------------------------------------------

_ROUTER_TMPL = '''\
"""
{name} module router aggregator.

컨벤션: AppRegistry 가 이 모듈의 ``{name}_router`` 를 발견해 /api 에 마운트한다.
버전별 서브라우터를 여기에 include 한다. 예:
    from app.features.{name}.api.routers.v1 import {name} as {name}_v1
    {name}_router.include_router({name}_v1.router, prefix="/v1/{name}", tags=["{Class}"])
"""

from fastapi import APIRouter

{name}_router = APIRouter()
'''

_DEPS_TMPL = '''\
"""
{Class} 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합해 view 에 제공한다.
**Dependency 는 조립만 한다** — commit 하지 않고 Service 메서드를 미리 실행하지도
않는다. 트랜잭션 경계는 쓰기 핸들러 본문이 `await service.commit()` 으로 닫는다.

예전 템플릿은 `yield` 뒤에서 commit 했는데, FastAPI 상위 버전에서 yield dependency
의 종료 코드가 **응답 전송 후에** 실행되도록 바뀌면서 커밋 실패가 201 로 둔갑했다.
그래서 커밋을 핸들러 본문으로 옮겼다.

조회는 read-only, 변경은 writer Dependency 를 쓴다. 쓰기용을 조회에 재사용하면
조회마다 불필요한 COMMIT 왕복이 생기고 한 세션에 커밋 주체가 둘이 될 수 있다.

예시:
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db.session import get_read_only_db_session, get_writer_db_session
    from app.features.{name}.services.{name}_service import {Class}Service

    async def get_{name}_service(
        session: AsyncSession = Depends(get_writer_db_session),
    ) -> {Class}Service:
        return {Class}Service(session)

    async def get_{name}_service_readonly(
        session: AsyncSession = Depends(get_read_only_db_session),
    ) -> {Class}Service:
        return {Class}Service(session)
"""
'''

_ADMIN_TMPL = '''\
"""
{Class} domain SQLAdmin views.

컨벤션: 모듈 레벨 ``admin_views`` 리스트를 두면 AppRegistry.install_admin 이
자동으로 SQLAdmin 에 등록한다(중앙 파일 수정 불필요).

활성화하려면 placeholder 를 실제 모델 기반 ModelView 로 교체한다:
    from sqladmin import ModelView
    from app.features.{name}.models.models import {Class}Model

    class {Class}Admin(ModelView, model={Class}Model):
        column_list = "__all__"

    admin_views = [{Class}Admin]
"""

# 아직 등록된 뷰 없음 — 위에 ModelView 를 추가하고 admin_views 에 넣으세요.
admin_views: list[type] = []
'''

# ---------------------------------------------------------------------------
# Required directory structure (relative to app root)
# ---------------------------------------------------------------------------

_REQUIRED_DIRS = [
    "api/routers/v1",
    "models",
    "schemas",
    "services",
    "repositories",
    "dependencies",
    "tests",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> None:
    """앱 이름이 파이썬 패키지로 쓸 수 있는지 검사한다.

    식별자가 아니면 자동 발견이 import 할 수 없어 **조용히 누락**된다
    (`pkgutil` 이 훑어도 `import` 단계에서 걸린다). 경로 구분자나 `..` 는
    `app/features` 바깥에 파일을 쓰게 만든다.
    """
    if not name or not name.isidentifier():
        raise ValueError(
            f"앱 이름 {name!r} 은 파이썬 식별자가 아닙니다. "
            "snake_case 로 지어 주세요 (예: order_items). "
            "식별자가 아니면 자동 발견이 import 하지 못해 조용히 누락됩니다."
        )
    if keyword.iskeyword(name):
        raise ValueError(f"앱 이름 {name!r} 은 파이썬 예약어라 쓸 수 없습니다.")


def scaffold(
    name: str,
    root: pathlib.Path,
    category: str = "domain",
    with_admin: bool = False,
    force: bool = False,
) -> None:
    """Generate ``app/features/<name>/`` scaffolding under *root*.

    Args:
        name: Snake-case app name (e.g. ``"orders"``).
        root: Project root directory (the one containing ``app/``).
        category: 예약(미사용) — 호환을 위해 시그니처만 유지.
        with_admin: If True, create ``admin.py`` (with empty ``admin_views``).
        force: 대상이 이미 있어도 덮어쓴다. 기본은 거부(작성한 코드 보호).

    Raises:
        ValueError: 이름이 식별자가 아니거나 예약어이거나, 계산된 경로가
            ``app/features`` 를 벗어나는 경우.
        FileExistsError: 대상 앱이 이미 있고 ``force`` 가 아닌 경우.

    Note:
        생성된 앱은 디렉터리 컨벤션만으로 AppRegistry 에 자동 발견된다.
        중앙 등록 목록(자매 저장소 passive 의 config.INSTALLED_APPS 같은) 수정이 필요 없다.
    """
    _validate_name(name)

    features_root = (root / "app" / "features").resolve()
    base = (features_root / name).resolve()

    # 이름 검증을 통과해도 경로를 한 번 더 확인한다 — 검증과 경로 계산이
    # 어긋나면(심링크 등) 그 틈으로 바깥에 파일이 생긴다.
    if base.parent != features_root:
        raise ValueError(f"앱 경로가 app/features 를 벗어납니다: {base}")

    # 덮어쓰기 방지. 같은 명령을 실수로 두 번 치면 작성한 코드가 사라지는데,
    # 되돌릴 방법이 없다. 정말 필요하면 force 로 의사를 명시하게 한다.
    if base.exists() and not force:
        raise FileExistsError(
            f"앱이 이미 있습니다: {base}. "
            "기존 코드를 덮어쓰지 않으려고 중단합니다. "
            "정말 다시 만들려면 --force 를 주세요."
        )

    class_name = "".join(part.capitalize() for part in name.split("_"))

    # Create required directory tree; each segment gets an __init__.py.
    for rel in _REQUIRED_DIRS:
        full = base / rel
        full.mkdir(parents=True, exist_ok=True)
        _touch_init_chain(base, rel)

    # App root __init__.py (import-time 부수효과가 필요하면 여기에 추가)
    (base / "__init__.py").touch()

    # Core files
    (base / "api" / "routers" / "router.py").write_text(
        _ROUTER_TMPL.format(name=name, Class=class_name),
        encoding="utf-8",
    )
    (base / "dependencies" / f"{name}_dependencies.py").write_text(
        _DEPS_TMPL.format(name=name, Class=class_name),
        encoding="utf-8",
    )

    # Optional: admin
    if with_admin:
        (base / "admin.py").write_text(
            _ADMIN_TMPL.format(name=name, Class=class_name),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _touch_init_chain(base: pathlib.Path, rel: str) -> None:
    """Create ``__init__.py`` in every directory segment of *rel* under *base*."""
    parts = pathlib.PurePosixPath(rel).parts
    current = base
    for part in parts:
        current = current / part
        init = current / "__init__.py"
        if not init.exists():
            init.touch()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.new_app",
        description="Scaffold a new FastAPI domain app (convention-based).",
    )
    p.add_argument("name", help="Snake-case app name (e.g. orders)")
    p.add_argument("--category", default="domain", help="Reserved (unused; kept for compatibility)")
    p.add_argument("--with-admin", action="store_true", help="Create admin.py")
    p.add_argument(
        "--force",
        action="store_true",
        help="앱이 이미 있어도 덮어쓴다 (기본은 거부 — 작성한 코드 보호)",
    )
    return p


def main() -> None:
    """CLI 진입점.

    안내문에는 한글과 em dash 가 섞여 있는데, Windows 한국어 콘솔(cp949)은 em dash 를
    인코딩하지 못한다. 그대로 두면 앱은 정상 생성됐는데 **프로세스가 1 로 죽어서**
    `python -m scripts.new_app x && <다음 단계>` 같은 조합이 조용히 끊긴다.
    안내문은 사람이 읽는 부가 정보이므로, 표현할 수 없는 글자는 대체하고 넘어간다.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    args = _build_parser().parse_args()
    scaffold(
        args.name,
        root=pathlib.Path.cwd(),
        category=args.category,
        with_admin=args.with_admin,
        force=args.force,
    )
    name = args.name
    class_name = "".join(part.capitalize() for part in name.split("_"))
    print(f"created app/features/{name}")
    print()
    print("이 앱은 디렉터리 컨벤션으로 자동 발견됩니다 — 중앙 파일 수정 불필요.")
    print(f"  - router: api/routers/router.py 의 {name}_router 가 /api 에 자동 마운트")
    print("  - models: models/ 에 ORM 모델을 두면 Base.metadata 에 자동 등록")
    if args.with_admin:
        print(f"  - admin: admin.py 의 admin_views 에 {class_name}Admin 을 추가하면 자동 노출")
    print("  - 서버 재시작 시 라우터가 마운트됩니다")


if __name__ == "__main__":
    main()
