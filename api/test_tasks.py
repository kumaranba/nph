"""Tests for the Celery billing task and its schedule wiring."""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings

from api.models import Admission, AdmissionStatus, Patient
from api.tasks import generate_due_invoices


def _active_admission():
    patient = Patient.objects.create(
        name="Due Patient", diagnosis="d", admitting_doctor="Dr",
    )
    # Admitted well over a month ago, so the current cycle is due today.
    return Admission.objects.create(
        patient=patient,
        admission_date=date.today() - timedelta(days=40),
        monthly_fee=Decimal("1000"),
        status=AdmissionStatus.ACTIVE,
    )


def test_task_generates_due_invoices_and_is_idempotent(db):
    admission = _active_admission()

    created = generate_due_invoices()
    assert created == 1
    assert admission.invoices.count() == 1

    # Re-running the same day creates nothing more.
    assert generate_due_invoices() == 0
    assert admission.invoices.count() == 1


def test_task_returns_zero_when_nothing_due(db):
    # No active admissions → nothing to bill.
    assert generate_due_invoices() == 0


def test_task_is_registered_with_celery(db):
    from config.celery import app
    assert "api.tasks.generate_due_invoices" in app.tasks


def test_beat_schedule_runs_daily_at_9am():
    entry = settings.CELERY_BEAT_SCHEDULE["generate-invoices-daily"]
    assert entry["task"] == "api.tasks.generate_due_invoices"
    schedule = entry["schedule"]
    assert 9 in schedule.hour
    assert 0 in schedule.minute
