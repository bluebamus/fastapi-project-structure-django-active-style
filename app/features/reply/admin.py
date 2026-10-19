"""
Reply 기능 SQLAdmin 설정

SQLAdmin 을 사용한 Reply 모델의 관리자 인터페이스를 정의한다.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN_DISABLED=false(기본): /admin 마운트 — 활성 슈퍼유저 로그인 필요
    (``app/features/auth/admin_auth.py``). ADMIN_DISABLED=true: /admin 자체가 없음(404).
    관리 화면을 쓰지 않는 배포는 ADMIN_DISABLED=true 로 둔다.
"""

from sqladmin import ModelView
from sqladmin.filters import OperationColumnFilter

from app.core.admin_filters import LocalDateFilter
from app.features.reply.models.models import Reply


class ReplyAdmin(ModelView, model=Reply):
    """
    Reply 관리자 뷰

    댓글/답글을 조회·생성·수정·삭제하는 관리자 인터페이스다.
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "댓글"
    name_plural = "댓글"
    icon = "fa-solid fa-comments"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # 본문(content)은 Text 컬럼이라 목록에서는 제외한다(상세에서 확인).
    # sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도 쓴다.
    column_list = [
        Reply.id,
        Reply.post_id,
        Reply.author,
        Reply.created_at,
        Reply.updated_at,
    ]

    # 기본 정렬 (최신순)
    column_default_sort = [(Reply.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    column_searchable_list = [
        Reply.content,
        Reply.author,
        Reply.post_id,
    ]

    # 필터는 sqladmin 0.32 의 필터 클래스로 준다 — 모델 컬럼을 그대로 넣으면 목록 페이지가
    # 500 이다(`parameter_name` 없음, admin-login F-006). 문자열·숫자는 OperationColumnFilter,
    # bool 은 BooleanFilter. created_at(UTCDateTime)은 core 의 LocalDateFilter — 업무 시간대
    # (TIME_ZONE) 날짜를 UTC 범위로 바꿔 질의한다(기본 연산 필터는 문자열을 그대로 바인딩해 500).
    column_filters = [
        LocalDateFilter(Reply.created_at),
        OperationColumnFilter(Reply.author),
        OperationColumnFilter(Reply.post_id),
    ]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    column_details_list = [
        Reply.id,
        Reply.content,
        Reply.author,
        Reply.post_id,
        Reply.created_at,
        Reply.updated_at,
    ]

    # =========================================================================
    # 권한 설정
    # =========================================================================
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    can_export = True
    export_types = ["csv", "json"]

    # =========================================================================
    # 폼 설정
    # =========================================================================
    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    # 손으로 넣으면 일관성이 깨지므로 폼에서 제외한다.
    form_excluded_columns = [Reply.id, Reply.created_at, Reply.updated_at]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
    column_labels = {
        Reply.id: "ID",
        Reply.content: "본문",
        Reply.author: "작성자",
        Reply.post_id: "게시글 ID",
        Reply.created_at: "생성 시각",
        Reply.updated_at: "수정 시각",
    }


# AppRegistry 가 이 모듈의 ``admin_views`` 를 자동으로 발견해 SQLAdmin 에 등록한다.
# 패키지 __init__.py 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
# sqladmin 이 딸려 와 ADMIN_DISABLED=true 가 무의미해진다(가드: tests/test_admin_wiring.py).
admin_views: list[type] = [ReplyAdmin]
