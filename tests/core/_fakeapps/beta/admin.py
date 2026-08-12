"""가짜 앱의 SQLAdmin 뷰 — `admin_views` 컨벤션을 만족하는 정상 사례."""

from sqladmin import ModelView

from tests.core._fakeapps.beta.models import Gadget, Widget


class WidgetAdmin(ModelView, model=Widget):
    name = "Widget"


class GadgetAdmin(ModelView, model=Gadget):
    name = "Gadget"


admin_views: list[type] = [WidgetAdmin, GadgetAdmin]
