def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")
    # 태스크는 중앙 app/celery/tasks.py 에 include 로 등록된다 (앱별 worker 제거).
    assert "app.celery.tasks" in celery_app.conf.include


def test_celery_keeps_internal_times_in_utc():
    """ETA·만료·결과 시각은 UTC 로 다룬다(ADR-007). TIME_ZONE 은 beat 표시용으로만 남는다."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE
