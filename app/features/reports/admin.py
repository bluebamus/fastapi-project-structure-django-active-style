"""Reports 도메인 SQLAdmin view.

컨벤션: 모듈 레벨 ``admin_views`` 를 두면 `AppRegistry.install_admin` 이 자동으로
등록한다(중앙 파일 수정 불필요).

## 왜 읽기 전용인가

매출 원본은 **회계 기록**이다. 화면에서 한 건 고치면 이미 마감된 일별 집계가 조용히
달라지고, 그 차이는 감사 시점에야 드러난다. 그래서 생성·수정·삭제를 모두 막고
조회와 내보내기만 연다 (SCN-RAW-001).

## 개인 식별자

`customer_email` 은 목록과 export 에서 제외한다. export 는 파일로 떨어져 메일·메신저로
옮겨 다니므로 화면보다 유출 경로가 길다. 상세 화면에도 두지 않는다 — 매출 리포트
운영자에게 주문자 이메일이 필요한 유스케이스가 없다.
"""

from sqladmin import ModelView

from app.features.reports.models.models import SalesOrder


class SalesOrderAdmin(ModelView, model=SalesOrder):
    """매출 원본 조회 화면 — 읽기 전용."""

    name = "Sales Order"
    name_plural = "Sales Orders"
    column_list = [
        SalesOrder.id,
        SalesOrder.order_no,
        SalesOrder.total_amount,
        SalesOrder.created_at,
    ]
    column_details_exclude_list = [SalesOrder.customer_email]
    column_export_list = [
        SalesOrder.id,
        SalesOrder.order_no,
        SalesOrder.total_amount,
        SalesOrder.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True


admin_views: list[type] = [SalesOrderAdmin]
