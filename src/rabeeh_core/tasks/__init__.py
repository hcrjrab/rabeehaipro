"""Async task execution via Celery with Redis broker.

Graceful degradation: when Celery/Redis is unavailable, the API falls back to
synchronous in-process execution (same behaviour as Phase 1).
"""
