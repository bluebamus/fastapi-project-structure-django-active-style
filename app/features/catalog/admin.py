"""Catalog 도메인 SQLAdmin view.

컨벤션: 모듈 레벨 ``admin_views`` 를 두면 `AppRegistry.install_admin` 이 자동으로
등록한다(중앙 파일 수정 불필요). registry 는 `admin.py` 부재를 선택 기능으로
취급하지만, 이 프로젝트는 신규 영속 모델의 Admin 누락을 허용하지 않는다.
"""

from sqladmin import ModelView

from app.core.admin_filters import LocalDateFilter
from app.features.catalog.models.models import Product


class ProductAdmin(ModelView, model=Product):
    """상품 관리 화면 — 전 기능 허용(운영자가 상품을 직접 관리한다)."""

    name = "Product"
    name_plural = "Products"
    column_list = [Product.id, Product.name, Product.price, Product.is_active, Product.created_at]
    # created_at(UTCDateTime)은 업무 시간대 날짜로 거른다(core LocalDateFilter).
    column_filters = [LocalDateFilter(Product.created_at)]
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    # 서버가 채우는 열은 폼에서 뺀다 — 폼의 시각 입력은 타임존이 없어 UTCDateTime 이 거부한다(F-003).
    form_excluded_columns = [Product.id, Product.created_at, Product.updated_at]


admin_views: list[type] = [ProductAdmin]
