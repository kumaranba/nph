"""Tests for recordPatientPayment (advance / multi-month payments)."""
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Invoice,
    InvoiceStatus,
    Patient,
    Room,
)

RECORD = """
mutation Record($patientId: ID!, $amount: Decimal!, $paidOn: Date!) {
  recordPatientPayment(patientId: $patientId, amount: $amount, paidOn: $paidOn) {
    patientId
    totalRecorded
    monthsCovered
    creditRemaining
    allocations { period amount }
  }
}
"""


@pytest.fixture
def patient_admission(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", age=72, diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    admission = Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("15000.00"),
        status=AdmissionStatus.ACTIVE,
    )
    return patient, admission


def _vars(patient, amount):
    return {"patientId": str(patient.id), "amount": amount, "paidOn": "2026-01-20"}


def test_advance_payment_covers_multiple_months(finance_client, patient_admission):
    patient, admission = patient_admission
    # Current invoice already exists (Jan 15 - Feb 14).
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))

    # Pay 3 months up front (3 x 15000).
    result = finance_client.execute(RECORD, _vars(patient, "45000.00"))
    assert result.get("errors") is None
    data = result["data"]["recordPatientPayment"]
    assert data["monthsCovered"] == 3
    assert Decimal(str(data["totalRecorded"])) == Decimal("45000.00")
    assert Decimal(str(data["creditRemaining"])) == Decimal("0.00")
    # Three consecutive monthly periods, all fully paid.
    periods = [a["period"] for a in data["allocations"]]
    assert periods == ["2026-01", "2026-02", "2026-03"]

    assert Invoice.objects.filter(admission=admission).count() == 3
    assert all(i.status == InvoiceStatus.PAID for i in admission.invoices.all())


def test_payment_clears_existing_outstanding_first(finance_client, patient_admission):
    patient, admission = patient_admission
    inv = BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))

    # Pay exactly one month -> clears the current invoice, no advance.
    result = finance_client.execute(RECORD, _vars(patient, "15000.00"))
    data = result["data"]["recordPatientPayment"]
    assert data["monthsCovered"] == 1
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID
    assert Invoice.objects.filter(admission=admission).count() == 1  # no future invoice


def test_partial_advance_leaves_last_invoice_partial(finance_client, patient_admission):
    patient, admission = patient_admission
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))

    # 1.5 months worth: current invoice paid, next invoice half paid.
    result = finance_client.execute(RECORD, _vars(patient, "22500.00"))
    data = result["data"]["recordPatientPayment"]
    assert data["monthsCovered"] == 2
    assert Decimal(str(data["creditRemaining"])) == Decimal("0.00")
    invs = list(admission.invoices.order_by("billing_period_start"))
    assert invs[0].status == InvoiceStatus.PAID
    assert invs[1].status == InvoiceStatus.PARTIAL
    assert BillingService.balance_due(invs[1]) == Decimal("7500.00")


def test_advance_with_no_existing_invoice(finance_client, patient_admission):
    patient, admission = patient_admission
    # No invoice generated yet; paying 2 months should create and pay two.
    result = finance_client.execute(RECORD, _vars(patient, "30000.00"))
    data = result["data"]["recordPatientPayment"]
    assert data["monthsCovered"] == 2
    assert Invoice.objects.filter(admission=admission).count() == 2


def test_admin_can_record_patient_payment(admin_client, patient_admission):
    patient, _ = patient_admission
    result = admin_client.execute(RECORD, _vars(patient, "15000.00"))
    assert result.get("errors") is None
    assert result["data"]["recordPatientPayment"]["monthsCovered"] == 1


def test_nurse_cannot_record_patient_payment(nurse_client, patient_admission):
    patient, _ = patient_admission
    result = nurse_client.execute(RECORD, _vars(patient, "15000.00"))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_rejects_non_positive_amount(finance_client, patient_admission):
    patient, _ = patient_admission
    result = finance_client.execute(RECORD, _vars(patient, "0"))
    assert result["data"] is None
    assert "must be positive" in result["errors"][0]["message"]
