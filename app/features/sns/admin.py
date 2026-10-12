"""
SNS 기능 SQLAdmin 설정

SQLAdmin 을 사용한 SnsPost 모델의 관리자 인터페이스를 정의한다.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN_DISABLED=false(기본): /admin 마운트 — 활성 슈퍼유저 로그인 필요
    (``app/features/auth/admin_auth.py``). ADMIN_DISABLED=true: /admin 자체가 없음(404).
    관리 화면을 쓰지 않는 배포는 ADMIN_DISABLED=true 로 둔다.
"""

from sqladmin import ModelView
from sqladmin.filters import OperationColumnFilter

from app.features.sns.models.models import SnsPost


class SnsPostAdmin(ModelView, model=SnsPost):
    """
    SnsPost 관리자 뷰

    SNS 피드 게시물을 조회·생성·수정·삭제하는 관리자 인터페이스다.
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "SNS 게시물"
    name_plural = "SNS 게시물"
    icon = "fa-solid fa-share-nodes"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # 본문(content)은 Text 컬럼이라 목록에서는 제외한다(상세에서 확인).
    # sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도 쓴다.
    column_list = [
        SnsPost.id,
        SnsPost.author,
        SnsPost.like_count,
        SnsPost.created_at,
        SnsPost.updated_at,
    ]

    # 기본 정렬 (최신순)
    column_default_sort = [(SnsPost.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    column_searchable_list = [
        SnsPost.content,
        SnsPost.author,
    ]

    # 필터는 sqladmin 0.32 의 필터 클래스로 준다 — 모델 컬럼을 그대로 넣으면 목록 페이지가
    # 500 이다(`parameter_name` 없음, admin-login F-006). 문자열·숫자는 OperationColumnFilter,
    # bool 은 BooleanFilter. created_at(UTCDateTime)은 OperationColumnFilter 가 문자열을 그대로
    # 바인딩해 naive/문자열 거부에 걸리므로 필터에서 뺐다 — 정렬로 본다(residual-risk R-310).
    column_filters = [
        OperationColumnFilter(SnsPost.author),
        OperationColumnFilter(SnsPost.like_count),
    ]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    column_details_list = [
        SnsPost.id,
        SnsPost.content,
        SnsPost.author,
        SnsPost.like_count,
        SnsPost.created_at,
        SnsPost.updated_at,
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
    form_excluded_columns = [SnsPost.id, SnsPost.created_at, SnsPost.updated_at]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
    column_labels = {
        SnsPost.id: "ID",
        SnsPost.content: "본문",
        SnsPost.author: "작성자",
        SnsPost.like_count: "좋아요 수",
        SnsPost.created_at: "생성 시각",
        SnsPost.updated_at: "수정 시각",
    }


# AppRegistry 가 이 모듈의 ``admin_views`` 를 자동으로 발견해 SQLAdmin 에 등록한다.
# 패키지 __init__.py 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
# sqladmin 이 딸려 와 ADMIN_DISABLED=true 가 무의미해진다(가드: tests/test_admin_wiring.py).
admin_views: list[type] = [SnsPostAdmin]
