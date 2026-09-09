"""A back-dated discharge must not bill full fees for cycles that start after
the discharge date (the patient wasn't present). Regression for the bug where
proration only touched the invoice containing the discharge date, leaving a
later month's invoice at full fee.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService, build_discharge_preview
from api.models import (
    Admission, AdmissionStatus, Fee, Invoice, InvoiceStatus, Patient,
)


@pytest.fixture
def two_cycles(db):
    """Admitted 10-Jan at 30000/mo. Billing has raised both the Jan cycle
    (10-Jan → 09-Feb) and the Feb cycle (10-Feb → 09-Mar) at full fee. The
    patient actually left 05-Feb (inside the Jan cycle)."""
    patient = Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 10),
        monthly_fee=Decimal("30000"), status=AdmissionStatus.ACTIVE,
    )
    fee = Fee.objects.create(
        admission=adm, amount=Decimal("30000"), effective_from=date(2026, 1, 10),
        is_active=True, reason="t",
    )
    jan = Invoice.objects.create(
        admission=adm, fee=fee,
        billing_period_start=date(2026, 1, 10), billing_period_end=date(2026, 2, 9),
        base_fee=Decimal("30000"), total_due=Decimal("30000"),
        status=InvoiceStatus.UNPAID,
    )
    feb = Invoice.objects.create(
        admission=adm, fee=fee,
        billing_period_start=date(2026, 2, 10), billing_period_end=date(2026, 3, 9),
        base_fee=Decimal("30000"), total_due=Decimal("30000"),
        status=InvoiceStatus.UNPAID,
    )
    return adm, jan, feb


# 27 of 31 days stayed in the Jan cycle → 30000 * 27/31.
PRORATED_JAN = Decimal("26129.03")
DISCHARGE = date(2026, 2, 5)


def test_preview_excludes_post_discharge_month(two_cycles):
    adm, jan, feb = two_cycles
    pv = build_discharge_preview(adm, DISCHARGE)
    # Only the pro-rated Jan cycle is owed; the Feb cycle (starts after the
    # discharge date) must not appear as a full month.
    assert pv.total_due_now == PRORATED_JAN


def test_apply_cancels_post_discharge_invoice(two_cycles):
    adm, jan, feb = two_cycles
    BillingService.apply_discharge_proration(adm, DISCHARGE)
    jan.refresh_from_db()
    feb.refresh_from_db()
    assert jan.base_fee == PRORATED_JAN            # containing cycle pro-rated
    assert feb.base_fee == Decimal("0")            # later cycle cancelled
    assert feb.total_due == Decimal("0")
    assert BillingService.total_pending_dues(adm) == PRORATED_JAN
