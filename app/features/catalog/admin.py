"""Catalog 도메인 SQLAdmin view.

컨벤션: 모듈 레벨 ``admin_views`` 를 두면 `AppRegistry.install_admin` 이 자동으로
등록한다(중앙 파일 수정 불필요). registry 는 `admin.py` 부재를 선택 기능으로
취급하지만, 이 프로젝트는 신규 영속 모델의 Admin 누락을 허용하지 않는다.
"""

from sqladmin import ModelView

from app.features.catalog.models.models import Product


class ProductAdmin(ModelView, model=Product):
    """상품 관리 화면 — 전 기능 허용(운영자가 상품을 직접 관리한다)."""

    name = "Product"
    name_plural = "Products"
    column_list = [Product.id, Product.name, Product.price, Product.is_active, Product.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True


admin_views: list[type] = [ProductAdmin]
