"""실제 앱을 import 해 대상 인벤토리를 JSON 한 줄로 낸다 (integration-e2e W3).

하네스가 e2e 환경 변수·`.env` 없는 cwd 로 자식 프로세스에서 실행한다 — 테스트 프로세스가 앱을 import 하면
저장소의 `.env` 가 섞인다. 출력: OpenAPI 문서, operation 별 선언 접근 수준, 관리 뷰와 가능한 동작,
Celery 태스크·beat 스케줄.
"""

import json
import logging

logging.disable(logging.CRITICAL)

import main  # noqa: E402
from app.celery.app import celery_app  # noqa: E402
from app.core.security.access import AccessPolicyGuard  # noqa: E402

celery_app.loader.import_default_modules()
admin = getattr(main, "admin", None)
print(
    "INVENTORY:"
    + json.dumps(
        {
            "openapi": main.app.openapi(),
            "access": {
                f"{method} {path}": sorted(levels)
                for (method, path), levels in AccessPolicyGuard().operations(main.app).items()
            },
            "admin_views": [
                {
                    "name": type(view).__name__,
                    "identity": view.identity,
                    "details": view.can_view_details,
                    "create": view.can_create,
                    "edit": view.can_edit,
                    "delete": view.can_delete,
                    "export": view.can_export,
                    "export_types": list(view.export_types),
                    "date_filter": any(
                        type(f).__name__ == "LocalDateFilter" for f in view.column_filters
                    ),
                    # @action 은 GET 이라 CSRF 밖이다 — 0 이어야 한다(계획서 §1.8).
                    "actions": sorted(
                        {**view._custom_actions_in_list, **view._custom_actions_in_detail}
                    ),
                }
                for view in (admin._views if admin else [])
            ],
            "tasks": sorted(t for t in celery_app.tasks if not t.startswith("celery.")),
            "beat": {
                name: {"task": entry["task"], "schedule": str(entry["schedule"])}
                for name, entry in celery_app.conf.beat_schedule.items()
            },
        }
    )
)
