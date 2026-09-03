"""Tests for the discharge waiver (administrative concession).

A waiver writes off part/all of the outstanding balance at discharge without
cash: it stamps ``waived_amount`` on invoices (clearing dues everywhere), keeps
a Waiver audit row, and shows on the statement as a non-cash credit. Admin and
Finance may waive; a reason is required.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.models import (
    Admission, AdmissionStatus, Fee, Invoice, InvoiceStatus, Patient,
    PaymentReceipt, Waiver,
)
from api.schema import build_account_statement

DISCHARGE = """
mutation Discharge(
  $id: ID!, $feesPaid: Decimal, $waiverAmount: Decimal, $waiverReason: String
) {
  dischargePatient(
    admissionId: $id, feesPaid: $feesPaid,
    waiverAmount: $waiverAmount, waiverReason: $waiverReason
  ) {
    waivedAmount
    admission { status }
  }
}
"""


@pytest.fixture
def dues(db):
    patient = Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("5000"), status=AdmissionStatus.ACTIVE,
    )
    fee = Fee.objects.create(
        admission=adm, amount=Decimal("5000"), effective_from=date(2026, 1, 1),
        is_active=True, reason="t",
    )
    # An old, fully-in-the-past month so discharge pro-ration is a no-op on it.
    Invoice.objects.create(
        admission=adm, fee=fee,
        billing_period_start=date(2026, 1, 1), billing_period_end=date(2026, 1, 31),
        base_fee=Decimal("5000"), total_due=Decimal("5000"),
        status=InvoiceStatus.UNPAID,
    )
    return patient, adm


# --- apply_waiver unit ----------------------------------------------------

def test_apply_waiver_clears_dues_and_records_audit(dues):
    patient, adm = dues
    applied = BillingService.apply_waiver(adm, Decimal("5000"), "hardship", None)
    assert applied == Decimal("5000")
    assert BillingService.total_pending_dues(adm) == Decimal("0")
    inv = adm.invoices.get()
    assert inv.waived_amount == Decimal("5000")
    assert inv.status == InvoiceStatus.PAID
    w = Waiver.objects.get()
    assert w.amount == Decimal("5000") and w.reason == "hardship"


def test_apply_waiver_caps_at_outstanding(dues):
    _, adm = dues
    applied = BillingService.apply_waiver(adm, Decimal("9000"), "x", None)
    assert applied == Decimal("5000")             # never more than owed
    assert Waiver.objects.get().amount == Decimal("5000")


# --- discharge with waiver ------------------------------------------------

def test_full_waiver_discharges_without_cash(admin_client, dues):
    patient, adm = dues
    r = admin_client.execute(DISCHARGE, {
        "id": str(adm.id), "waiverAmount": "5000", "waiverReason": "hardship",
    })
    assert r.get("errors") is None
    assert r["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"
    assert Decimal(r["data"]["dischargePatient"]["waivedAmount"]) == Decimal("5000")
    assert BillingService.total_pending_dues(adm) == Decimal("0")
    # No cash receipt was created for the waiver.
    assert PaymentReceipt.objects.filter(admission=adm).count() == 0
    assert Waiver.objects.filter(admission=adm).count() == 1


def test_partial_waiver_plus_payment(finance_client, dues):
    _, adm = dues
    r = finance_client.execute(DISCHARGE, {
        "id": str(adm.id), "feesPaid": "3000",
        "waiverAmount": "2000", "waiverReason": "goodwill",
    })
    assert r.get("errors") is None
    assert r["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"
    assert BillingService.total_pending_dues(adm) == Decimal("0")
    # The cash part is a real receipt; the waiver is not.
    assert PaymentReceipt.objects.filter(admission=adm).count() == 1
    assert Waiver.objects.get(admission=adm).amount == Decimal("2000")


def test_waiver_requires_reason(admin_client, dues):
    _, adm = dues
    r = admin_client.execute(DISCHARGE, {"id": str(adm.id), "waiverAmount": "5000"})
    assert r["errors"]
    adm.refresh_from_db()
    assert adm.status == AdmissionStatus.ACTIVE          # blocked
    assert Waiver.objects.count() == 0


def test_partial_waiver_alone_still_blocks_discharge(admin_client, dues):
    _, adm = dues
    # Waive only 2000 of 5000, pay nothing → 3000 still owed → hard block.
    r = admin_client.execute(DISCHARGE, {
        "id": str(adm.id), "waiverAmount": "2000", "waiverReason": "partial",
    })
    assert r["errors"]
    assert "outstanding" in r["errors"][0]["message"].lower()
    adm.refresh_from_db()
    assert adm.status == AdmissionStatus.ACTIVE
    # Rolled back — no partial waiver persisted.
    assert Waiver.objects.count() == 0
    assert adm.invoices.get().waived_amount == Decimal("0")


# --- statement ------------------------------------------------------------

def test_waiver_shows_on_statement_as_noncash_credit(finance_client, dues):
    patient, adm = dues
    finance_client.execute(DISCHARGE, {
        "id": str(adm.id), "waiverAmount": "5000", "waiverReason": "hardship",
    })
    st = build_account_statement(patient.id)
    labels = [ln.description for ln in st.lines]
    assert "Waiver (concession)" in labels
    assert st.closing_balance == Decimal("0")          # dues cleared
    # The waiver is not counted as cash received.
    assert st.total_credits == Decimal("5000")         # the waiver credit
    assert PaymentReceipt.objects.filter(admission=adm).count() == 0
