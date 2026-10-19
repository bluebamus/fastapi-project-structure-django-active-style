"""
User 기능 SQLAdmin 설정

SQLAdmin 을 사용한 User 모델의 관리자 인터페이스를 정의한다.

보안 주의:
    ``User`` 는 auth 기능이 쓰는 자격증명(``hashed_password``)을 보유한다.
    sqladmin 은 ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세
    페이지와 수정 폼에 **모델의 모든 컬럼**을 넣는다. 따라서 아무 설정도 하지 않으면
    bcrypt 해시가 관리 화면에 그대로 노출되고, 폼에서 임의 문자열로 덮어쓸 수도 있다.
    아래 두 줄이 그 노출 경로를 차단한다 — 지우지 말 것.

        column_details_exclude_list = [User.hashed_password]
        form_excluded_columns = [..., User.hashed_password]

    ``can_create = False`` 도 같은 이유다. 폼에서 비밀번호를 제외한 채 생성을 허용하면
    ``hashed_password`` 가 비어 있는 계정이 만들어지고, auth 는 그런 계정을 영구히
    거부하므로(로그인 불가) 조용히 깨진 데이터가 쌓인다.
    구조 증거: ``tests/core/test_admin_views.py``.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN_DISABLED=false(기본): /admin 마운트 — 활성 슈퍼유저 로그인 필요
    (``app/features/auth/admin_auth.py``). ADMIN_DISABLED=true: /admin 자체가 없음(404).
    관리 화면을 쓰지 않는 배포는 ADMIN_DISABLED=true 로 둔다.
"""

from typing import Any

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter
from starlette.requests import Request

from app.core.admin_filters import LocalDateFilter
from app.core.security.admin_session import session_store_of
from app.core.security.dependencies import get_refresh_token_store, get_token_service
from app.features.user.models.models import User
from app.features.user.services.user_service import revoke_user_access


class UserAdmin(ModelView, model=User):
    """
    User 관리자 뷰

    사용자를 조회·수정·삭제하는 관리자 인터페이스다. 생성은 지원하지 않는다.
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "사용자"
    name_plural = "사용자"
    icon = "fa-solid fa-user"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # hashed_password 없음. sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도
    # 쓰므로, 여기서 빠지면 내보내기 파일에도 해시가 들어가지 않는다.
    column_list = [
        User.id,
        User.username,
        User.email,
        User.is_active,
        User.created_at,
    ]

    # 기본 정렬 (최신 가입순)
    column_default_sort = [(User.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    column_searchable_list = [
        User.username,
        User.email,
    ]

    # 필터는 sqladmin 0.32 의 필터 클래스로 준다 — 모델 컬럼을 그대로 넣으면 목록 페이지가
    # 500 이다(`parameter_name` 없음, admin-login F-006). 문자열·숫자는 OperationColumnFilter,
    # bool 은 BooleanFilter. created_at(UTCDateTime)은 core 의 LocalDateFilter — 업무 시간대
    # (TIME_ZONE) 날짜를 UTC 범위로 바꿔 질의한다(기본 연산 필터는 문자열을 그대로 바인딩해 500).
    column_filters = [
        LocalDateFilter(User.created_at),
        BooleanFilter(User.is_active),
    ]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    # 포함 목록이 아니라 제외 목록을 쓴다. 새 컬럼이 모델에 추가되면 상세에 자동으로
    # 따라 붙되, 자격증명만은 무조건 빠진다.
    column_details_exclude_list = [User.hashed_password]

    # =========================================================================
    # 권한 설정
    # =========================================================================
    # 생성 차단: 폼에서 비밀번호를 제외한 채 생성을 허용하면 hashed_password 가 NULL 인
    # 계정이 만들어진다. 모델이 nullable 이라 DB 는 받아주지만 auth 서비스는 그런 계정을
    # 영구히 거부하므로(로그인 불가), 목록에는 멀쩡해 보이는 죽은 계정이 쌓인다.
    # 가입은 auth 도메인의 API 를 통해서만 이루어진다.
    can_create = False

    can_edit = True
    can_delete = True
    can_view_details = True

    can_export = True
    export_types = ["csv", "json"]

    # =========================================================================
    # 폼 설정
    # =========================================================================
    # 자격증명은 폼에 노출하지 않는다(비밀번호 변경은 auth 도메인 담당).
    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    form_excluded_columns = [
        User.id,
        User.hashed_password,
        User.created_at,
        User.updated_at,
    ]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
    column_labels = {
        User.id: "ID",
        User.username: "사용자명",
        User.email: "이메일",
        User.is_active: "활성 여부",
        User.created_at: "가입 시각",
        User.updated_at: "수정 시각",
    }

    # =========================================================================
    # 접근 즉시 폐기 (admin-session-hardening ADR-008 — ADR-007 대체)
    # =========================================================================
    # 관리 화면에서 비활성화·슈퍼유저 해제·비밀번호 해시 변경·삭제하면 그 사용자의 /admin 세션과
    # API refresh 토큰을 전부 끊는다(``revoke_user_access`` — UserService 와 같은 폐기 집합). 다른 브라우저
    # 포함, 자기 자신이면 지금 세션도. 일반 수정은 유지한다.
    # 커밋 **전** 훅(on_model_change·on_model_delete)에서 부른다 — sqladmin 0.32 는 이 훅을 세션 안,
    # commit 앞에서 부르므로 Redis 오류가 나면 예외가 commit 을 건너뛰고(롤백) sqladmin 이 오류를
    # 폼·목록에 그린다. "DB 는 비활성화됨 + 세션은 살아 있음" 이 남지 않는다.
    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        if is_created:
            return
        before = {f: getattr(model, f, None) for f in _REVOKING_FIELDS}
        after = {f: data.get(f, before[f]) for f in _REVOKING_FIELDS}  # 폼에 없는 필드는 그대로
        if loses_admin_access(before, after):
            await _revoke(request, model.id)

    async def on_model_delete(self, model: Any, request: Request) -> None:
        await _revoke(request, model.id)


_REVOKING_FIELDS = ("is_active", "is_superuser", "hashed_password")


def loses_admin_access(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """비활성화·슈퍼유저 해제·비밀번호 해시 변경이면 참(접근을 끊어야 한다)."""
    return bool(
        (before["is_active"] and not after["is_active"])
        or (before["is_superuser"] and not after["is_superuser"])
        or before["hashed_password"] != after["hashed_password"]
    )


async def _revoke(request: Request, user_id: str) -> None:
    """이 요청의 Redis(세션 미들웨어의 저장소)로 refresh 저장소를 만들어 같은 폐기 집합을 부른다."""
    sessions = session_store_of(request)
    refresh = get_refresh_token_store(sessions.redis, get_token_service())
    await revoke_user_access(refresh, sessions, user_id)


# AppRegistry 가 이 모듈의 ``admin_views`` 를 자동으로 발견해 SQLAdmin 에 등록한다.
# 패키지 __init__.py 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
# sqladmin 이 딸려 와 ADMIN_DISABLED=true 가 무의미해진다(가드: tests/test_admin_wiring.py).
admin_views: list[type] = [UserAdmin]
