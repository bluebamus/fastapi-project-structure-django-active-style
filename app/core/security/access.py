"""뷰 단위 접근 수준 선언과 기본 거부 정책 (access-policy ADR-001~003).

모든 API 뷰는 경로 데코레이터의 ``dependencies=[...]`` 에 접근 수준 하나를 선언한다::

    @router.get("/posts", dependencies=[Public])
    @router.post("/register", dependencies=[PublicWrite])
    @router.get("/me", dependencies=[LoginRequired])
    @router.delete("/{id}", dependencies=[SuperuserRequired])

사용자 정보가 필요한 뷰는 인자 ``principal: CurrentPrincipal`` / ``SuperuserPrincipal`` 로
받는다 — 그 인자도 각각 LoginRequired / SuperuserRequired 선언으로 인정한다.

함수를 감싸는 Django 식 ``@login_required`` 는 만들지 않는다. FastAPI 는 뷰 함수의
시그니처로 주입·검증·OpenAPI 를 만들기 때문에 감싸면 그 셋이 함께 깨진다.

데코레이터만으로는 "선언을 잊은 뷰" 가 열린 채 배포된다. 그래서 ``AccessPolicyGuard`` 가
앱 조립 직후 모든 라우트를 훑어 선언이 없거나 모순인 뷰가 있으면 기동을 멈춘다(기본 거부).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fastapi import Depends
from fastapi.routing import APIRoute, iter_route_contexts

from app.core.registry import AppContractError
from app.core.security.dependencies import get_current_principal, require_superuser

if TYPE_CHECKING:  # pragma: no cover - 타입 검사 전용
    from fastapi import FastAPI
    from fastapi.dependencies.models import Dependant


def public() -> None:
    """표식 — 인증 없이 읽는다. 아무것도 하지 않는다."""


def public_write() -> None:
    """표식 — 인증 없이 쓴다(가입·로그인·refresh·logout). 아무것도 하지 않는다."""


Public = Depends(public)
PublicWrite = Depends(public_write)
LoginRequired = Depends(get_current_principal)
SuperuserRequired = Depends(require_superuser)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class AccessLevel(StrEnum):
    PUBLIC = "Public"
    PUBLIC_WRITE = "PublicWrite"
    LOGIN = "LoginRequired"
    SUPERUSER = "SuperuserRequired"


_MARKERS: dict[Callable[..., Any], AccessLevel] = {
    public: AccessLevel.PUBLIC,
    public_write: AccessLevel.PUBLIC_WRITE,
}


class AccessPolicyGuard:
    """앱이 서빙하는 모든 APIRoute 의 접근 수준 선언을 검사한다.

    대상은 ``APIRoute`` 전부다(``include_in_schema=False`` 포함, 중첩 include 펼침).
    Starlette ``Route``(openapi.json 등)와 ``Mount``(/admin — 자체 세션 인증)는 대상이 아니다.
    """

    def declared_levels(self, dependant: Dependant) -> frozenset[AccessLevel]:
        """의존성 트리에서 찾은 접근 수준들. 정상이면 원소가 정확히 하나다.

        ``require_superuser`` 는 내부에서 ``get_current_principal`` 을 쓰므로 둘 다 있으면
        슈퍼유저 하나로 본다.
        """
        calls = set(self._calls(dependant))
        levels = {level for marker, level in _MARKERS.items() if marker in calls}
        if require_superuser in calls:
            levels.add(AccessLevel.SUPERUSER)
        elif get_current_principal in calls:
            levels.add(AccessLevel.LOGIN)
        return frozenset(levels)

    def operations(self, app: FastAPI) -> dict[tuple[str, str], frozenset[AccessLevel]]:
        """``(메서드, 경로 템플릿)`` → 선언된 접근 수준."""
        result: dict[tuple[str, str], frozenset[AccessLevel]] = {}
        for context in iter_route_contexts(app.routes):
            if not isinstance(context.original_route, APIRoute):
                continue
            # 중첩 include 로 붙은 라우트는 context 가 prefix 를 합친 경로·의존성 트리를 갖는다.
            path = context.path or context.original_route.path
            levels = self.declared_levels(context.dependant)
            for method in sorted(context.methods or ()):
                result[(method, path)] = levels
        return result

    def violations(self, app: FastAPI) -> list[str]:
        problems: list[str] = []
        for (method, path), levels in self.operations(app).items():
            where = f"{method} {path}"
            names = ", ".join(sorted(levels))
            if not levels:
                problems.append(
                    f"{where}: 접근 수준 선언이 없습니다 — dependencies=[Public | PublicWrite | "
                    "LoginRequired | SuperuserRequired] 중 하나를 적으세요."
                )
            elif len(levels) > 1:
                problems.append(f"{where}: 접근 수준이 둘 이상입니다({names}) — 하나만 두세요.")
            elif AccessLevel.PUBLIC in levels and method not in SAFE_METHODS:
                problems.append(
                    f"{where}: 쓰기 메서드에 Public 을 썼습니다 — 인증 없는 쓰기는 "
                    "PublicWrite 로 명시하세요."
                )
            elif AccessLevel.PUBLIC_WRITE in levels and method in SAFE_METHODS:
                problems.append(
                    f"{where}: 안전한 메서드에 PublicWrite 를 썼습니다 — Public 을 쓰세요."
                )
        return problems

    def verify(self, app: FastAPI) -> None:
        """위반이 하나라도 있으면 전부 담아 ``AppContractError`` 로 기동을 멈춘다."""
        problems = self.violations(app)
        if problems:
            raise AppContractError(
                f"접근 수준 정책 위반 {len(problems)}건 — 서버를 기동하지 않습니다:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )

    def _calls(self, dependant: Dependant) -> Iterator[Callable[..., Any] | None]:
        yield dependant.call
        for sub in dependant.dependencies:
            yield from self._calls(sub)
