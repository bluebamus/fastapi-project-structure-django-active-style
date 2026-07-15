"""
User 모듈 SQLAdmin 설정

SQLAdmin 을 사용한 User 모델의 관리자 인터페이스를 정의한다.

Note:
    이 저장소의 ``User`` 는 자격증명(비밀번호 해시)을 보유하지 않는다. 따라서 관리
    화면에서 사용자를 생성해도 로그인 불가 계정이 만들어질 위험이 없어 생성을 허용한다.
    (auth 도메인을 가진 저장소에서는 ``hashed_password`` 컬럼을 상세·폼에서 제외하고
    생성을 차단해야 한다 — sqladmin 은 지정이 없으면 상세·폼에 모든 컬럼을 넣는다.)

    SQLAdmin 은 ADMIN 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN=True: /admin 접근 가능, ADMIN=False: /admin 접근 차단
    운영 환경에서는 보안상 ADMIN=False 설정을 권장한다.
"""

from sqladmin import ModelView

from app.domains.user.models.models import User


class UserAdmin(ModelView, model=User):
    """
    User 관리자 뷰

    사용자를 조회·생성·수정·삭제하는 관리자 인터페이스다.
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
    # sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도 쓴다.
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

    column_filters = [
        User.is_active,
        User.created_at,
    ]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    column_details_list = [
        User.id,
        User.username,
        User.email,
        User.is_active,
        User.created_at,
        User.updated_at,
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
    form_excluded_columns = [User.id, User.created_at, User.updated_at]

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


# 컨벤션: AppRegistry.install_admin 이 이 모듈 레벨 리스트를 SQLAdmin 에 등록한다.
admin_views: list[type] = [UserAdmin]
