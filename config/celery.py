"""Celery application for the NPH project.

Reads all Celery configuration from Django settings (keys prefixed ``CELERY_``)
and autodiscovers ``tasks.py`` in each installed app. Started by the worker and
beat processes:

    celery -A config worker -l info
    celery -A config beat -l info
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("nph")
# All CELERY_* settings in Django settings.py configure this app.
app.config_from_object("django.conf:settings", namespace="CELERY")
# Discover @shared_task definitions (e.g. api/tasks.py).
app.autodiscover_tasks()
