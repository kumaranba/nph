"""Tests for BillingService — cycle-date math and invoice generation."""
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    ChargeCategory,
    Invoice,
    Patient,
    Room,
    User,
    UserRole,
)


@pytest.fixture
def staff(db):
    return User.objects.create_user(
        email="finance@billing.test", password="x", role=UserRole.FINANCE
    )


def _admission(admission_date, *, monthly_fee="25000.00", label="A1"):
    room = Room.objects.create(name="Ward", capacity=5)
    bed = Bed.objects.create(room=room, label=label, status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", age=72, diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    return Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=admission_date,
        monthly_fee=Decimal(monthly_fee),
        status=AdmissionStatus.ACTIVE,
    )


# --------------------------------------------------------------- cycle dates
@pytest.mark.parametrize(
    "anchor, month, year, expected",
    [
        # 31st anchor clamps to a short month (Feb).
        (date(2026, 1, 31), 2, 2026, date(2026, 2, 28)),
        # Leap year — Feb has 29 days.
        (date(2024, 1, 31), 2, 2024, date(2024, 2, 29)),
        # 31st anchor in a 30-day month.
        (date(2026, 1, 31), 4, 2026, date(2026, 4, 30)),
        # Mid-month anchor is untouched.
        (date(2026, 1, 15), 3, 2026, date(2026, 3, 15)),
    ],
)
def test_get_billing_cycle_date_handles_short_months(anchor, month, year, expected):
    assert BillingService.get_billing_cycle_date(anchor, month, year) == expected


# ------------------------------------------------------ invoice generation
def test_first_invoice_created_on_admission_day(db):
    admission = _admission(date(2026, 1, 15))

    invoice = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )

    assert invoice.billing_period_start == date(2026, 1, 15)
    assert invoice.billing_period_end == date(2026, 2, 14)  # day before next cycle
    assert invoice.base_fee == Decimal("25000.00")
    assert invoice.total_due == Decimal("25000.00")
    assert invoice.status == "UNPAID"


def test_admission_on_31st_billing_into_february(db):
    # Admitted Jan 31 — the first period ends the day before the Feb cycle date,
    # which clamps to Feb 28, so the period is Jan 31 -> Feb 27.
    admission = _admission(date(2026, 1, 31))

    first = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 31)
    )
    assert first.billing_period_start == date(2026, 1, 31)
    assert first.billing_period_end == date(2026, 2, 27)

    # The Feb-anchored period itself starts on the clamped Feb 28.
    feb = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 2, 28)
    )
    assert feb.billing_period_start == date(2026, 2, 28)
    assert feb.billing_period_end == date(2026, 3, 30)


def test_invoice_includes_additional_charges_in_period(db, staff):
    admission = _admission(date(2026, 1, 15))  # period Jan 15 -> Feb 14

    # Two charges inside the period, one in the next period.
    AdditionalCharge.objects.create(
        admission=admission, category=ChargeCategory.DRUGS,
        amount=Decimal("500.00"), charge_date=date(2026, 1, 20), recorded_by=staff,
    )
    AdditionalCharge.objects.create(
        admission=admission, category=ChargeCategory.SNACKS,
        amount=Decimal("300.00"), charge_date=date(2026, 2, 10), recorded_by=staff,
    )
    AdditionalCharge.objects.create(
        admission=admission, category=ChargeCategory.OTHER,
        amount=Decimal("999.00"), charge_date=date(2026, 2, 20), recorded_by=staff,
    )

    invoice = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )
    # 25000 base + 500 + 300 (the Feb 20 charge is out of period).
    assert invoice.total_due == Decimal("25800.00")


def test_duplicate_invoice_not_created_for_same_period(db):
    admission = _admission(date(2026, 1, 15))

    first = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )
    again = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 20)  # same period, different day
    )

    assert again.id == first.id
    assert Invoice.objects.filter(admission=admission).count() == 1


def test_no_invoice_before_admission_day(db):
    admission = _admission(date(2026, 1, 15))
    assert (
        BillingService.generate_invoice_for_admission(
            admission.id, as_of=date(2026, 1, 14)
        )
        is None
    )
    assert Invoice.objects.count() == 0


def test_generate_all_due_invoices_is_idempotent_and_skips_discharged(db):
    active1 = _admission(date(2026, 1, 10), label="A1")
    active2 = _admission(date(2026, 1, 20), label="A2")
    discharged = _admission(date(2026, 1, 5), label="A3")
    discharged.status = AdmissionStatus.DISCHARGED
    discharged.save(update_fields=["status"])

    created = BillingService.generate_all_due_invoices(as_of=date(2026, 1, 25))
    assert len(created) == 2  # both active admissions, not the discharged one
    assert Invoice.objects.filter(admission=discharged).count() == 0

    # Second run creates nothing new.
    again = BillingService.generate_all_due_invoices(as_of=date(2026, 1, 25))
    assert again == []
    assert Invoice.objects.count() == 2
