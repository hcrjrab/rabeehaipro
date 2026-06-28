"""Celery worker entrypoint for the ``rabeeh-worker`` console script.

Usage:
    rabeeh-worker
"""

from __future__ import annotations

import sys


def main() -> None:
    """Start the Celery worker using the project's configured app."""
    from rabeeh_core.tasks.celery_app import celery_app

    argv = [
        "rabeeh-worker",
        "-A",
        "rabeeh_core.tasks.celery_app",
        "worker",
        "--loglevel=info",
    ]
    sys.exit(celery_app.start(argv))
