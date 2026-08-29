"""Tests for post-discharge take-home medication on ``dischargePatient``.

At discharge the family may buy a one-month drug supply. It is billed as a
DRUGS additional charge (dated the discharge day) and paid, in its own receipt,
into the Pharmacy payment account — so it shows on the patient statement and the
pharmacy money is tracked separately. Because the charge and its payment are
always created together, they never affect the discharge hard-block; leaving the
amount blank discharges exactly as before.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import (
    AdditionalCharge, Admission, AdmissionStatus, ChargeCategory, Fee, Invoice,
    InvoiceStatus, Patient, PaymentAccount, PaymentReceipt,
)
from api.schema import build_account_statement


DISCHARGE = """
mutation Discharge(
  $admissionId: ID!
  $feesPaid: Decimal
  $medicationAmount: Decimal
  $medicationNote: String
) {
  dischargePatient(
    admissionId: $admissionId
    feesPaid: $feesPaid
    medicationAmount: $medicationAmount
    medicationNote: $medicationNote
  ) {
    admission { status }
  }
}
"""


@pytest.fixture
def admission(db):
    # Zero monthly fee so the current-cycle pro-ration is 0 and these tests
    # isolate the medication behaviour (which is independent of the fee amount).
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="d", admitting_doctor="Dr",
    )
    return Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("0.00"), status=AdmissionStatus.ACTIVE,
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


def test_pharmacy_account_is_seeded(db):
    assert PaymentAccount.objects.filter(name="Pharmacy").exists()


def test_medication_billed_and_paid_into_pharmacy(admin_client, admission):
    # No dues; buy ₹500 of take-home drugs.
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(admission.id),
        "medicationAmount": "500.00",
        "medicationNote": "1-month supply",
    })
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"

    # A DRUGS charge dated the discharge day.
    charge = AdditionalCharge.objects.get(admission=admission)
    assert charge.category == ChargeCategory.DRUGS
    assert charge.amount == Decimal("500.00")
    assert charge.charge_date == date.today()
    assert "1-month supply" in charge.description

    # Paid into the Pharmacy account, as its own receipt.
    pharmacy = PaymentAccount.objects.get(name="Pharmacy")
    receipt = PaymentReceipt.objects.get(admission=admission, account=pharmacy)
    assert receipt.amount == Decimal("500.00")
    assert receipt.charges_amount == Decimal("500.00")

    # Nothing left owing — the charge and payment net out.
    from api.billing import BillingService
    assert BillingService.total_pending_dues(admission) == Decimal("0")


def test_medication_shows_on_account_statement(admin_client, admission):
    admin_client.execute(DISCHARGE, {
        "admissionId": str(admission.id), "medicationAmount": "500.00",
    })
    stmt = build_account_statement(admission.patient_id)
    debits = [ln for ln in stmt.lines if ln.debit > 0]
    credits = [ln for ln in stmt.lines if ln.credit > 0]
    assert any("Drugs" in ln.description and ln.debit == Decimal("500.00") for ln in debits)
    assert any("Pharmacy" in ln.description and ln.credit == Decimal("500.00") for ln in credits)


def test_no_medication_discharges_normally(admin_client, admission):
    result = admin_client.execute(DISCHARGE, {"admissionId": str(admission.id)})
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"
    assert AdditionalCharge.objects.filter(admission=admission).count() == 0
    assert PaymentReceipt.objects.filter(admission=admission).count() == 0


def test_medication_alongside_dues(admin_client, admission):
    # ₹25000 owed for January; also buy ₹500 of drugs. Fees settle the month;
    # the medication is collected separately into Pharmacy.
    _invoice(admission, date(2026, 1, 1), date(2026, 1, 31))
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(admission.id),
        "feesPaid": "25000.00",
        "medicationAmount": "500.00",
    })
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"
    pharmacy = PaymentAccount.objects.get(name="Pharmacy")
    assert PaymentReceipt.objects.filter(
        admission=admission, account=pharmacy, amount=Decimal("500.00")
    ).exists()
    from api.billing import BillingService
    assert BillingService.total_pending_dues(admission) == Decimal("0")


def test_negative_medication_rejected(admin_client, admission):
    result = admin_client.execute(DISCHARGE, {
        "admissionId": str(admission.id), "medicationAmount": "-5",
    })
    assert result["errors"]
    admission.refresh_from_db()
    assert admission.status == AdmissionStatus.ACTIVE   # rolled back


def test_finance_can_add_medication(finance_client, admission):
    result = finance_client.execute(DISCHARGE, {
        "admissionId": str(admission.id), "medicationAmount": "300.00",
    })
    assert result.get("errors") is None
    assert result["data"]["dischargePatient"]["admission"]["status"] == "DISCHARGED"
    assert AdditionalCharge.objects.filter(
        admission=admission, category=ChargeCategory.DRUGS
    ).exists()
