"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tradesignal",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scan_tasks",
        "app.tasks.monitor_tasks",
        "app.tasks.news_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_track_started=True,
    task_time_limit=600,  # 10 min max per task
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
)

# ═══════════════════════════════════════════════════════════════════════════
#  PERIODIC TASK SCHEDULE (Celery Beat)
# ═══════════════════════════════════════════════════════════════════════════

celery_app.conf.beat_schedule = {
    # Monitor open positions every 30 min during market hours (9:15-15:30 IST, Mon-Fri)
    "monitor-positions-30min": {
        "task": "app.tasks.monitor_tasks.monitor_open_positions",
        "schedule": crontab(minute="*/30", hour="9-15", day_of_week="1-5"),
    },

    # Scan breaking news every 15 min during market hours
    "scan-news-15min": {
        "task": "app.tasks.news_tasks.scan_breaking_news",
        "schedule": crontab(minute="*/15", hour="9-16", day_of_week="1-5"),
    },

    # Weekly full scan — Sunday 6 PM IST
    "weekly-full-scan": {
        "task": "app.tasks.scan_tasks.weekly_scan",
        "schedule": crontab(minute=0, hour=18, day_of_week=0),
    },

    # Daily performance computation — weekdays 4 PM IST (after market close)
    "daily-performance": {
        "task": "app.tasks.monitor_tasks.compute_daily_performance",
        "schedule": crontab(minute=0, hour=16, day_of_week="1-5"),
    },
}
