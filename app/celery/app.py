"""중앙 Celery 앱.

모든 도메인의 백그라운드 태스크는 app/celery/tasks.py 에 중앙 집중한다.
앱별 worker/ 디렉토리는 제거되었으며 이 패키지(app/celery)가 대체한다.
"""

from celery import Celery

from app.celery.worker_lifecycle import register_worker_signals
from config import redis_settings, timezone_settings

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 앱 전역 타임존 설정(TIME_ZONE)을 따른다(하드코딩 대신 설정 일원화).
    timezone=timezone_settings.TIME_ZONE,
    enable_utc=False,
    beat_schedule={},
)

# prefork 자식 프로세스의 자원 생명주기를 연결한다 (ADR-005).
# fork 로 상속된 커넥션 풀을 버리지 않으면 부모·자식이 같은 소켓을 공유해 MySQL
# 패킷 순서가 엉킨다. solo/threads 풀에서는 이 신호가 오지 않으므로 no-op 이다.
register_worker_signals()
