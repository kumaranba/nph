"""Tests for the createCharge and deleteCharge mutations."""
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
    Invoice,
    InvoiceStatus,
    Patient,
    Room,
    User,
    UserRole,
)

CREATE_CHARGE = """
mutation CreateCharge(
  $admissionId: ID!
  $category: ChargeCategoryEnum!
  $amount: Decimal!
  $chargeDate: Date!
  $description: String
) {
  createCharge(
    admissionId: $admissionId
    category: $category
    amount: $amount
    chargeDate: $chargeDate
    description: $description
  ) {
    id
    category
    amount
    chargeDate
    description
  }
}
"""

DELETE_CHARGE = """
mutation DeleteCharge($chargeId: ID!) {
  deleteCharge(chargeId: $chargeId)
}
"""


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", age=72, diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    return Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )


def _charge_vars(admission, **overrides):
    data = {
        "admissionId": str(admission.id),
        "category": "DRUGS",
        "amount": "500.00",
        "chargeDate": "2026-01-20",
        "description": "Antibiotics",
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------- createCharge
def test_finance_can_create_charge(finance_client, admission):
    result = finance_client.execute(CREATE_CHARGE, _charge_vars(admission))
    assert result.get("errors") is None
    charge = result["data"]["createCharge"]
    assert charge["category"] == "DRUGS"
    assert Decimal(str(charge["amount"])) == Decimal("500.00")
    assert AdditionalCharge.objects.filter(admission=admission).count() == 1


def test_charge_on_discharged_admission_rejected(finance_client, admission):
    admission.status = AdmissionStatus.DISCHARGED
    admission.save(update_fields=["status"])

    result = finance_client.execute(CREATE_CHARGE, _charge_vars(admission))
    assert result["data"] is None
    assert "discharged" in result["errors"][0]["message"].lower()
    assert AdditionalCharge.objects.count() == 0


def test_nurse_cannot_create_charge(nurse_client, admission):
    result = nurse_client.execute(CREATE_CHARGE, _charge_vars(admission))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    assert AdditionalCharge.objects.count() == 0


def test_admin_cannot_create_charge(admin_client, admission):
    # createCharge is FINANCE only.
    result = admin_client.execute(CREATE_CHARGE, _charge_vars(admission))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_charge_appears_in_invoice_for_its_period(finance_client, admission):
    # Charge dated within the Jan 15 -> Feb 14 period.
    finance_client.execute(CREATE_CHARGE, _charge_vars(admission, amount="800.00"))

    invoice = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )
    # 25000 base + 800 charge.
    assert invoice.total_due == Decimal("25800.00")
    charge = AdditionalCharge.objects.get(admission=admission)
    assert invoice.billing_period_start <= charge.charge_date <= invoice.billing_period_end


# --------------------------------------------------------------- deleteCharge
def test_finance_can_delete_uninvoiced_charge(finance_client, admission):
    created = finance_client.execute(CREATE_CHARGE, _charge_vars(admission))
    charge_id = created["data"]["createCharge"]["id"]

    result = finance_client.execute(DELETE_CHARGE, {"chargeId": charge_id})
    assert result.get("errors") is None
    assert result["data"]["deleteCharge"] is True
    assert AdditionalCharge.objects.count() == 0


def test_cannot_delete_charge_after_invoice_paid(finance_client, admission):
    created = finance_client.execute(CREATE_CHARGE, _charge_vars(admission))
    charge_id = created["data"]["createCharge"]["id"]

    # The charge auto-billed onto the period's invoice; pay it in full.
    inv = Invoice.objects.get(admission=admission, is_settlement=False)
    user = User.objects.create_user(
        email="pay@nph.test", password="secret123", role=UserRole.FINANCE
    )
    BillingService.record_payment_for_admission(
        admission, inv.total_due, Decimal("0"), date(2026, 1, 20), user
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID

    result = finance_client.execute(DELETE_CHARGE, {"chargeId": charge_id})
    assert result["data"] is None
    assert "already paid" in result["errors"][0]["message"].lower()
    assert AdditionalCharge.objects.count() == 1  # not deleted


def test_nurse_cannot_delete_charge(nurse_client, finance_client, admission):
    created = finance_client.execute(CREATE_CHARGE, _charge_vars(admission))
    charge_id = created["data"]["createCharge"]["id"]

    result = nurse_client.execute(DELETE_CHARGE, {"chargeId": charge_id})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    assert AdditionalCharge.objects.count() == 1
