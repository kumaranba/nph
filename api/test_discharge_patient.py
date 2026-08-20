"""Tests for the ``dischargePatient`` mutation and ``dischargePreview`` query.

New billing behaviour:
  * Discharge pro-rates the in-progress cycle's fee to the days actually stayed
    (start day through discharge day, both inclusive).
  * Discharge is HARD-BLOCKED while any balance remains — an optional payment is
    recorded first, and if anything is still owed the whole thing rolls back.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Fee,
    Invoice,
    InvoiceStatus,
    Patient,
    Room,
)

DISCHARGE = """
mutation Discharge(
  $admissionId: ID!
  $dischargeDate: Date
  $feesPaid: Decimal
  $chargesPaid: Decimal
  $refundAmount: Decimal
) {
  dischargePatient(
    admissionId: $admissionId
    dischargeDate: $dischargeDate
    feesPaid: $feesPaid
    chargesPaid: $chargesPaid
    refundAmount: $refundAmount
  ) {
    hasOutstandingDues
    outstandingInvoiceCount
    refundAmount
    admission { status dischargeDate bed { label status } }
  }
}
"""

PREVIEW = """
query Preview($admissionId: ID!, $dischargeDate: Date) {
  dischargePreview(admissionId: $admissionId, dischargeDate: $dischargeDate) {
    hasCurrentCycle
    fullFee daysInPeriod daysStayed proratedFee cancelledFee
    feesDue chargesDue totalDueNow
    lines { label kind amount }
  }
}
"""


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="Test Ward", capacity=1)
    bed = Bed.objects.create(room=room, label="T1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="Pneumonia", admitting_doctor="Dr. Smith",
    )
    return Admission.objects.create(
        patient=patient, bed=bed,
        admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )


def _invoice(admission, start, end, base=Decimal("25000.00")):
    fee = admission.active_fee or Fee.objects.create(
        admission=admission, amount=admission.monthly_fee,
        effective_from=admission.admission_date, is_active=True, reason="test",
    )
    return Invoice.objects.create(
        admission=admission, fee=fee,
        billing_period_start=start, billing_period_end=end,
        base_fee=base, total_due=base, status=InvoiceStatus.UNPAID,
    )


# --- clean discharge (nothing owed) ---------------------------------------

def test_admin_can_discharge_and_bed_is_freed(admin_client, admission):
    result = admin_client.execute(DISCHARGE, {"admissionId": str(admission.id)})
    assert result.get("errors") is None
    payload = result["data"]["dischargePatient"]
    assert payload["hasOutstandingDues"] is False
    assert payload["admission"]["status"] == "DISCHARGED"
    assert payload["admission"]["bed"]["status"] == "VACANT"

    admission.refresh_from_db()
    admission.bed.refresh_from_db()
    assert admission.status == AdmissionStatus.DISCHARGED
    assert admission.discharge_date == date.today()
    assert admission.bed.status == BedStatus.VACANT


# --- hard block ------------------------------------------------------------

def test_discharge_blocked_with_outstanding_dues(admin_client, admission):
    # An older unpaid month.
    _invoice(admission, date(2026, 1, 1), date(2026, 1, 31))
    result = admin_client.execute(DISCHARGE, {"admissionId": str(admission.id)})
    assert result["data"] is None
    assert "outstanding" in result["errors"][0]["message"].lower()
    # Rolled back — still admitted, bed still occupied.
    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.bed.status == BedStatus.OCCUPIED


def test_discharge_succeeds_when_dues_paid_in_full(admin_client, admission):
    _invoice(admission, date(2026, 1, 1), date(2026, 1, 31))
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(admission.id), "feesPaid": "25000.00",
    })
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"


# --- pro-ration ------------------------------------------------------------

@pytest.fixture
def mid_cycle(db):
    """Admitted 18-Jul, ₹20500/mo. The 18-Aug→17-Sep cycle (31 days) is billed
    in full; discharge on 20-Aug should pro-rate it to 3/31 days."""
    patient = Patient.objects.create(
        name="Mohanapriya", diagnosis="d", admitting_doctor="Dr",
    )
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 7, 18),
        monthly_fee=Decimal("20500.00"), status=AdmissionStatus.ACTIVE,
    )
    inv = _invoice(adm, date(2026, 8, 18), date(2026, 9, 17), base=Decimal("20500.00"))
    return adm, inv


def test_preview_prorates_current_cycle(admin_client, mid_cycle):
    adm, _ = mid_cycle
    result = admin_client.execute(
        PREVIEW, {"admissionId": str(adm.id), "dischargeDate": "2026-08-20"}
    )
    assert result.get("errors") is None
    pv = result["data"]["dischargePreview"]
    assert pv["hasCurrentCycle"] is True
    assert pv["daysInPeriod"] == 31 and pv["daysStayed"] == 3
    assert Decimal(pv["proratedFee"]) == Decimal("1983.87")
    assert Decimal(pv["cancelledFee"]) == Decimal("18516.13")
    assert Decimal(pv["totalDueNow"]) == Decimal("1983.87")


def test_discharge_prorates_invoice_and_succeeds_when_paid(admin_client, mid_cycle):
    adm, inv = mid_cycle
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(adm.id),
        "dischargeDate": "2026-08-20",
        "feesPaid": "1983.87",
    })
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"

    inv.refresh_from_db()
    assert inv.base_fee == Decimal("1983.87")      # reduced from 20500
    assert inv.total_due == Decimal("1983.87")
    assert inv.status == InvoiceStatus.PAID

    adm.refresh_from_db()
    assert adm.status == AdmissionStatus.DISCHARGED
    assert adm.discharge_date == date(2026, 8, 20)


def test_short_payment_rolls_back_everything(admin_client, mid_cycle):
    adm, inv = mid_cycle
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(adm.id),
        "dischargeDate": "2026-08-20",
        "feesPaid": "1000.00",     # less than the pro-rated 1983.87
    })
    assert result["data"] is None
    assert "outstanding" in result["errors"][0]["message"].lower()
    # Everything rolled back: invoice full, still admitted.
    inv.refresh_from_db()
    assert inv.base_fee == Decimal("20500.00")
    assert inv.status == InvoiceStatus.UNPAID
    adm.refresh_from_db()
    assert adm.status == AdmissionStatus.ACTIVE


# --- refunds & RBAC (unchanged contract) ----------------------------------

def test_finance_refund_is_logged(finance_client, admission):
    result = finance_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": "1500.00"}
    )
    assert result.get("errors") is None
    assert Decimal(str(result["data"]["dischargePatient"]["refundAmount"])) == Decimal("1500.00")
    admission.refresh_from_db()
    assert admission.refund_amount == Decimal("1500.00")
    assert admission.status == AdmissionStatus.DISCHARGED


def test_admin_cannot_record_refund(admin_client, admission):
    result = admin_client.execute(
        DISCHARGE, {"admissionId": str(admission.id), "refundAmount": "1500.00"}
    )
    assert result["data"] is None
    assert "Only Finance" in result["errors"][0]["message"]
    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.bed.status == BedStatus.OCCUPIED


def test_nurse_cannot_discharge(nurse_client, admission):
    result = nurse_client.execute(DISCHARGE, {"admissionId": str(admission.id)})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.bed.status == BedStatus.OCCUPIED


ADMISSION_DUES = """
query Admission($pk: ID!) {
  admission(pk: $pk) { hasOutstandingDues outstandingInvoiceCount }
}
"""


def test_admission_exposes_outstanding_dues_before_discharge(admin_client, admission):
    before = admin_client.execute(ADMISSION_DUES, {"pk": str(admission.id)})
    assert before["data"]["admission"]["hasOutstandingDues"] is False

    _invoice(admission, date(2026, 1, 1), date(2026, 1, 31))
    after = admin_client.execute(ADMISSION_DUES, {"pk": str(admission.id)})
    assert after["data"]["admission"]["hasOutstandingDues"] is True
    assert after["data"]["admission"]["outstandingInvoiceCount"] == 1
