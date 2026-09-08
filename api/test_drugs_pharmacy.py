"""Tests for routing drug-charge money to the Pharmacy account at collection.

A patient payment may carry a pharmacyAmount, recorded as its own receipt into
the Pharmacy account (distinct from fees / other charges). AdmissionType also
exposes outstandingDrugCharges as a guide for the payment form.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import (
    Admission, AdmissionStatus, AdditionalCharge, ChargeCategory, Fee,
    Invoice, InvoiceStatus, Patient, PaymentReceipt, User, UserRole,
)

PAY = """
mutation($pid: ID!, $fees: Decimal, $charges: Decimal, $pharmacy: Decimal) {
  recordPatientPayment(
    patientId: $pid, paidOn: "2026-02-20",
    feesAmount: $fees, chargesAmount: $charges, pharmacyAmount: $pharmacy
  ) {
    totalRecorded pharmacyAmount invoicesPaid
  }
}
"""

DRUG_DUE = """
query($pk: ID!) {
  patient(pk: $pk) { admissions { outstandingDrugCharges } }
}
"""


@pytest.fixture
def seeded(db):
    patient = Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
    )
    fee = Fee.objects.create(
        admission=adm, amount=Decimal("10000"), effective_from=date(2026, 1, 1),
        is_active=True, reason="t",
    )
    Invoice.objects.create(
        admission=adm, fee=fee,
        billing_period_start=date(2026, 1, 1), billing_period_end=date(2026, 1, 31),
        base_fee=Decimal("10000"), total_due=Decimal("10500"),
        status=InvoiceStatus.UNPAID,
    )
    staff = User.objects.create_user(
        email="rec@nph.test", password="secret123", role=UserRole.FINANCE
    )
    AdditionalCharge.objects.create(
        admission=adm, category=ChargeCategory.DRUGS, amount=Decimal("500"),
        charge_date=date(2026, 1, 10), recorded_by=staff,
    )
    return patient, adm


def test_pharmacy_amount_recorded_into_pharmacy_account(finance_client, seeded):
    patient, adm = seeded
    r = finance_client.execute(PAY, {
        "pid": str(patient.id), "fees": "10000", "charges": "0", "pharmacy": "500",
    })
    assert r.get("errors") is None
    data = r["data"]["recordPatientPayment"]
    assert Decimal(data["totalRecorded"]) == Decimal("10500")
    assert Decimal(data["pharmacyAmount"]) == Decimal("500")
    # The drug money is its own receipt on the Pharmacy account.
    pharmacy = PaymentReceipt.objects.get(admission=adm, account__name="Pharmacy")
    assert pharmacy.amount == Decimal("500")
    # The fee money is a separate receipt (default account / none here).
    assert PaymentReceipt.objects.filter(admission=adm).count() == 2


def test_pharmacy_only_payment(finance_client, seeded):
    patient, adm = seeded
    r = finance_client.execute(PAY, {
        "pid": str(patient.id), "fees": "0", "charges": "0", "pharmacy": "500",
    })
    assert r.get("errors") is None
    assert Decimal(r["data"]["recordPatientPayment"]["pharmacyAmount"]) == Decimal("500")
    assert PaymentReceipt.objects.filter(
        admission=adm, account__name="Pharmacy"
    ).count() == 1
    # No fee receipt was created.
    assert PaymentReceipt.objects.filter(admission=adm).count() == 1


def test_negative_pharmacy_rejected(finance_client, seeded):
    patient, _ = seeded
    r = finance_client.execute(PAY, {
        "pid": str(patient.id), "fees": "0", "charges": "0", "pharmacy": "-5",
    })
    assert r["errors"]


def test_zero_total_rejected(finance_client, seeded):
    patient, _ = seeded
    r = finance_client.execute(PAY, {
        "pid": str(patient.id), "fees": "0", "charges": "0", "pharmacy": "0",
    })
    assert r["errors"]


def test_outstanding_drug_charges_guide(finance_client, seeded):
    patient, _ = seeded
    r = finance_client.execute(DRUG_DUE, {"pk": str(patient.id)})
    assert r.get("errors") is None
    dd = r["data"]["patient"]["admissions"][0]["outstandingDrugCharges"]
    assert Decimal(dd) == Decimal("500")     # DRUGS in the unpaid period
