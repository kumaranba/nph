"""Ensure the Celery app is loaded when Django starts, so shared tasks register
and the app is importable as ``config.celery.app``."""
from .celery import app as celery_app

__all__ = ("celery_app",)
