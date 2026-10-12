"""중앙 Celery 앱 (ADR-009).

이 패키지는 Celery 앱 객체와 실행 기반(`task.run_async`·워커 생명주기)만 가진다.
태스크는 각 기능의 선택 모듈 `app/features/<name>/tasks.py` 에 두고, 워커의 include
목록과 모델 등록은 API 와 같은 `AppRegistry` 발견 결과에서 만든다 — 이 패키지는
기능을 import 하지 않는다. 앱 디렉터리를 지우면 그 앱의 태스크도 include 에서 빠지고,
워커는 import 오류 없이 뜬다.
"""

from celery import Celery

from app.celery.worker_lifecycle import register_worker_signals
from app.core.registry import AppRegistry
from config import redis_settings, timezone_settings

# 발견은 부작용이 없다. 모델은 API(main.py)와 같은 경로로 등록해 둔다 — 태스크가 쓰는
# 모델의 relationship 이 다른 앱 모델을 가리켜도 매퍼 구성이 실패하지 않는다.
registry = AppRegistry()
registry.discover()
registry.import_models()

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=registry.task_modules(),
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 내부 시각(ETA·만료·결과 date_done)은 UTC 로 다룬다 — DB 와 같은 정본(ADR-007).
    # timezone 은 beat crontab 을 지역 시각으로 해석·표시하는 데만 쓴다.
    timezone=timezone_settings.TIME_ZONE,
    enable_utc=True,
    beat_schedule={},
)

# prefork 자식 프로세스의 자원 생명주기를 연결한다 (ADR-005).
# fork 로 상속된 커넥션 풀을 버리지 않으면 부모·자식이 같은 소켓을 공유해 MySQL
# 패킷 순서가 엉킨다. solo/threads 풀에서는 이 신호가 오지 않으므로 no-op 이다.
register_worker_signals()
