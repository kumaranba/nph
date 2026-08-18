"""Tests for recordPatientPayment — advance payments held as patient credit."""
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
mutation Record($patientId: ID!, $feesAmount: Decimal!, $paidOn: Date!) {
  recordPatientPayment(
    patientId: $patientId, feesAmount: $feesAmount, paidOn: $paidOn
  ) {
    totalRecorded
    invoicesPaid
    creditAdded
    creditBalance
    allocations { period amount }
  }
}
"""


@pytest.fixture
def patient_admission(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="Pneumonia", admitting_doctor="Dr. X"
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
    return {"patientId": str(patient.id), "feesAmount": amount, "paidOn": "2026-01-20"}


def test_surplus_is_held_as_credit(finance_client, patient_admission):
    patient, admission = patient_admission
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))

    # Pay 3 months: clears the current invoice, holds 2 months as credit.
    result = finance_client.execute(RECORD, _vars(patient, "45000.00"))
    assert result.get("errors") is None
    data = result["data"]["recordPatientPayment"]
    assert data["invoicesPaid"] == 1
    assert Decimal(str(data["creditAdded"])) == Decimal("30000.00")
    assert Decimal(str(data["creditBalance"])) == Decimal("30000.00")
    # No future invoices are pre-generated — only the current one exists.
    assert Invoice.objects.filter(admission=admission).count() == 1
    admission.refresh_from_db()
    assert admission.credit_balance == Decimal("30000.00")


def test_credit_auto_applies_to_future_invoices(finance_client, patient_admission):
    patient, admission = patient_admission
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    finance_client.execute(RECORD, _vars(patient, "45000.00"))  # 30000 credit

    # Next month's invoice is generated -> credit pays it automatically.
    feb = BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 2, 15))
    assert feb.status == InvoiceStatus.PAID
    admission.refresh_from_db()
    assert admission.credit_balance == Decimal("15000.00")

    # And the following month too.
    mar = BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 3, 15))
    assert mar.status == InvoiceStatus.PAID
    admission.refresh_from_db()
    assert admission.credit_balance == Decimal("0.00")


def test_partial_credit_leaves_invoice_partial(finance_client, patient_admission):
    patient, admission = patient_admission
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    # 1.5 months: current paid, 7500 credit.
    finance_client.execute(RECORD, _vars(patient, "22500.00"))
    admission.refresh_from_db()
    assert admission.credit_balance == Decimal("7500.00")

    feb = BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 2, 15))
    assert feb.status == InvoiceStatus.PARTIAL
    assert BillingService.balance_due(feb) == Decimal("7500.00")
    admission.refresh_from_db()
    assert admission.credit_balance == Decimal("0.00")


def test_payment_clears_outstanding_before_crediting(finance_client, patient_admission):
    patient, admission = patient_admission
    inv = BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    # Exactly one month clears the current invoice, no credit.
    result = finance_client.execute(RECORD, _vars(patient, "15000.00"))
    data = result["data"]["recordPatientPayment"]
    assert data["invoicesPaid"] == 1
    assert Decimal(str(data["creditAdded"])) == Decimal("0.00")
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID


def test_payment_with_no_invoice_becomes_all_credit(finance_client, patient_admission):
    patient, admission = patient_admission
    # No invoice yet -> nothing to clear -> entire amount is credit.
    result = finance_client.execute(RECORD, _vars(patient, "30000.00"))
    data = result["data"]["recordPatientPayment"]
    assert data["invoicesPaid"] == 0
    assert Decimal(str(data["creditAdded"])) == Decimal("30000.00")
    assert Invoice.objects.filter(admission=admission).count() == 0


def test_admin_can_record_patient_payment(admin_client, patient_admission):
    patient, _ = patient_admission
    result = admin_client.execute(RECORD, _vars(patient, "15000.00"))
    assert result.get("errors") is None


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
