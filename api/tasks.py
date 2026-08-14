"""Celery tasks for the api app.

Scheduled by Celery Beat (see CELERY_BEAT_SCHEDULE in settings). Tasks are thin
wrappers around service logic so they stay testable and idempotent.
"""
import logging

from celery import shared_task

from .billing import BillingService

logger = logging.getLogger(__name__)


@shared_task(name="api.tasks.generate_due_invoices")
def generate_due_invoices() -> int:
    """Generate any invoices that have become due for active admissions.

    Idempotent — ``BillingService.generate_all_due_invoices`` skips periods
    that already have an invoice, so re-running (or an overlapping run) creates
    nothing extra. Returns the number of invoices created.
    """
    created = BillingService.generate_all_due_invoices()
    logger.info("generate_due_invoices: created %d invoice(s)", len(created))
    return len(created)
