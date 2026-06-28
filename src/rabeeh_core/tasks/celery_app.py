"""Celery application configured from project settings.

Usage:
    celery -A rabeeh_core.tasks.celery_app worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from ..config.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "rabeeh",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
