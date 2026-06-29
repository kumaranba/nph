"""Tests for the ``dischargePatient`` mutation.

Covers a clean discharge (status flipped, bed freed), the outstanding-dues
warning flag, a Finance-only refund being logged, and the NURSE role being
rejected.
"""
from datetime import date
from decimal import Decimal

import pytest

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

DISCHARGE = """
mutation Discharge(
  $admissionId: ID!
  $refundAmount: Decimal
) {
  dischargePatient(admissionId: $admissionId, refundAmount: $refundAmount) {
    hasOutstandingDues
    outstandingInvoiceCount
    refundAmount
    admission {
      status
      dischargeDate
      bed { label status }
    }
  }
}
"""


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="Test Ward", capacity=1)
    bed = Bed.objects.create(room=room, label="T1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe",
        age=72,
        diagnosis="Pneumonia",
        admitting_doctor="Dr. Smith",
    )
    return Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )


def _unpaid_invoice(admission):
    return Invoice.objects.create(
        admission=admission,
        billing_period_start=date(2026, 1, 1),
        billing_period_end=date(2026, 1, 31),
        base_fee=Decimal("25000.00"),
        total_due=Decimal("25000.00"),
        status=InvoiceStatus.UNPAID,
    )


def test_admin_can_discharge_and_bed_is_freed(admin_client, admission):
    result = admin_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": None}
    )

    assert result.get("errors") is None
    payload = result["data"]["dischargePatient"]
    assert payload["hasOutstandingDues"] is False
    assert payload["outstandingInvoiceCount"] == 0
    assert payload["admission"]["status"] == "DISCHARGED"
    assert payload["admission"]["bed"]["status"] == "VACANT"

    # Persisted: admission discharged, bed freed.
    admission.refresh_from_db()
    admission.bed.refresh_from_db()
    assert admission.status == AdmissionStatus.DISCHARGED
    assert admission.discharge_date == date.today()
    assert admission.bed.status == BedStatus.VACANT


def test_discharge_with_outstanding_dues_warns(admin_client, admission):
    _unpaid_invoice(admission)

    result = admin_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": None}
    )

    assert result.get("errors") is None
    payload = result["data"]["dischargePatient"]
    # The warning flag is raised, but the discharge still completes.
    assert payload["hasOutstandingDues"] is True
    assert payload["outstandingInvoiceCount"] == 1
    assert payload["admission"]["status"] == "DISCHARGED"


def test_finance_refund_is_logged(finance_client, admission):
    result = finance_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": "1500.00"}
    )

    assert result.get("errors") is None
    payload = result["data"]["dischargePatient"]
    assert Decimal(str(payload["refundAmount"])) == Decimal("1500.00")

    admission.refresh_from_db()
    assert admission.refund_amount == Decimal("1500.00")
    assert admission.status == AdmissionStatus.DISCHARGED


def test_admin_cannot_record_refund(admin_client, admission):
    # ADMIN may discharge, but only FINANCE may attach a refund.
    result = admin_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": "1500.00"}
    )

    assert result["data"] is None
    assert "Only Finance" in result["errors"][0]["message"]

    # Nothing was changed — still active, bed still occupied.
    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.bed.status == BedStatus.OCCUPIED


ADMISSION_DUES = """
query Admission($pk: ID!) {
  admission(pk: $pk) {
    hasOutstandingDues
    outstandingInvoiceCount
  }
}
"""


def test_admission_exposes_outstanding_dues_before_discharge(admin_client, admission):
    # No invoices yet — no dues.
    before = admin_client.execute(ADMISSION_DUES, {"pk": str(admission.id)})
    assert before["data"]["admission"]["hasOutstandingDues"] is False
    assert before["data"]["admission"]["outstandingInvoiceCount"] == 0

    _unpaid_invoice(admission)

    after = admin_client.execute(ADMISSION_DUES, {"pk": str(admission.id)})
    assert after["data"]["admission"]["hasOutstandingDues"] is True
    assert after["data"]["admission"]["outstandingInvoiceCount"] == 1


def test_nurse_cannot_discharge(nurse_client, admission):
    result = nurse_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": None}
    )

    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]

    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.bed.status == BedStatus.OCCUPIED
