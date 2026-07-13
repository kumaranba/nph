"""Tests for the invoice GraphQL queries and the Finance-only payment/refund
mutations.
"""
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

INVOICE = """
query Invoice($patientId: ID!, $period: String!) {
  invoice(patientId: $patientId, period: $period) {
    id
    baseFee
    totalDue
    amountPaid
    balanceDue
    status
    billingPeriodStart
  }
}
"""

INVOICE_LIST = """
query InvoiceList($patientId: ID!) {
  invoiceList(patientId: $patientId) {
    id
    billingPeriodStart
    totalDue
  }
}
"""

LOG_PAYMENT = """
mutation LogPayment($invoiceId: ID!, $amount: Decimal!, $paidOn: Date!) {
  logPayment(invoiceId: $invoiceId, amount: $amount, paidOn: $paidOn) {
    id
    status
    amountPaid
    balanceDue
  }
}
"""

LOG_REFUND = """
mutation LogRefund($invoiceId: ID!, $amount: Decimal!) {
  logRefund(invoiceId: $invoiceId, amount: $amount) {
    id
    status
    refundAmount
    balanceDue
  }
}
"""


@pytest.fixture
def invoice(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", age=72, diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    admission = Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )
    return BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )


# ------------------------------------------------------------------ queries
def test_invoice_query_by_patient_and_period(finance_client, invoice):
    patient_id = str(invoice.admission.patient_id)
    result = finance_client.execute(
        INVOICE, {"patientId": patient_id, "period": "2026-01"}
    )
    assert result.get("errors") is None
    data = result["data"]["invoice"]
    assert data["id"] == str(invoice.id)
    assert Decimal(str(data["totalDue"])) == Decimal("25000.00")
    assert Decimal(str(data["balanceDue"])) == Decimal("25000.00")
    assert data["status"] == "UNPAID"


def test_invoice_query_missing_period_returns_null(finance_client, invoice):
    patient_id = str(invoice.admission.patient_id)
    result = finance_client.execute(
        INVOICE, {"patientId": patient_id, "period": "2026-05"}
    )
    assert result.get("errors") is None
    assert result["data"]["invoice"] is None


def test_invoice_list_query(finance_client, invoice):
    patient_id = str(invoice.admission.patient_id)
    result = finance_client.execute(INVOICE_LIST, {"patientId": patient_id})
    assert result.get("errors") is None
    rows = result["data"]["invoiceList"]
    assert len(rows) == 1
    assert rows[0]["id"] == str(invoice.id)


# ---------------------------------------------------------------- mutations
def test_finance_log_payment_partial_then_paid(finance_client, invoice):
    # Partial payment -> PARTIAL.
    partial = finance_client.execute(
        LOG_PAYMENT,
        {"invoiceId": str(invoice.id), "amount": "10000.00", "paidOn": "2026-01-20"},
    )
    assert partial.get("errors") is None
    data = partial["data"]["logPayment"]
    assert data["status"] == "PARTIAL"
    assert Decimal(str(data["amountPaid"])) == Decimal("10000.00")
    assert Decimal(str(data["balanceDue"])) == Decimal("15000.00")

    # Pay the rest -> PAID.
    full = finance_client.execute(
        LOG_PAYMENT,
        {"invoiceId": str(invoice.id), "amount": "15000.00", "paidOn": "2026-01-25"},
    )
    paid = full["data"]["logPayment"]
    assert paid["status"] == "PAID"
    assert Decimal(str(paid["balanceDue"])) == Decimal("0.00")


def test_finance_log_refund_reduces_balance(finance_client, invoice):
    result = finance_client.execute(
        LOG_REFUND, {"invoiceId": str(invoice.id), "amount": "5000.00"}
    )
    assert result.get("errors") is None
    data = result["data"]["logRefund"]
    assert Decimal(str(data["refundAmount"])) == Decimal("5000.00")
    assert Decimal(str(data["balanceDue"])) == Decimal("20000.00")
    assert data["status"] == "PARTIAL"


def test_admin_can_log_payment(admin_client, invoice):
    # ADMIN may record payments too (not just FINANCE).
    result = admin_client.execute(
        LOG_PAYMENT,
        {"invoiceId": str(invoice.id), "amount": "10000.00", "paidOn": "2026-01-20"},
    )
    assert result.get("errors") is None
    assert result["data"]["logPayment"]["status"] == "PARTIAL"
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PARTIAL


def test_nurse_cannot_log_payment(nurse_client, invoice):
    result = nurse_client.execute(
        LOG_PAYMENT,
        {"invoiceId": str(invoice.id), "amount": "10000.00", "paidOn": "2026-01-20"},
    )
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_log_payment_rejects_non_positive_amount(finance_client, invoice):
    result = finance_client.execute(
        LOG_PAYMENT,
        {"invoiceId": str(invoice.id), "amount": "0", "paidOn": "2026-01-20"},
    )
    assert result["data"] is None
    assert "must be positive" in result["errors"][0]["message"]
