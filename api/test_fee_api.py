"""Tests for the changeFee mutation, feeHistory query, fee immutability on
generated invoices, and the verify_fee_migration command."""
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.billing import BillingService
from api.fees import FeeService
from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Fee,
    Patient,
    Room,
    User,
    UserRole,
)

CHANGE_FEE = """
mutation ChangeFee(
  $admissionId: ID!, $amount: Decimal!, $reason: String!,
  $effectiveFrom: Date, $override: Boolean
) {
  changeFee(
    admissionId: $admissionId, amount: $amount, reason: $reason,
    effectiveFrom: $effectiveFrom, override: $override
  ) {
    id amount effectiveFrom isActive reason
  }
}
"""

FEE_HISTORY = """
query FeeHistory($patientId: ID!) {
  feeHistory(patientId: $patientId) { id amount isActive }
}
"""


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", age=72, diagnosis="dx", admitting_doctor="Dr. X"
    )
    adm = Admission.objects.create(
        patient=patient, bed=bed, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("15000.00"), status=AdmissionStatus.ACTIVE,
    )
    Fee.objects.create(
        admission=adm, amount=Decimal("15000.00"), effective_from=date(2026, 1, 15),
        is_active=True, reason="Initial fee",
    )
    return adm


def _vars(admission, **over):
    data = {
        "admissionId": str(admission.id),
        "amount": "18000.00",
        "reason": "Annual revision",
        "effectiveFrom": None,
        "override": False,
    }
    data.update(over)
    return data


# ------------------------------------------------------------- changeFee (RBAC)
def test_finance_can_change_fee(finance_client, admission):
    result = finance_client.execute(CHANGE_FEE, _vars(admission))
    assert result.get("errors") is None
    fee = result["data"]["changeFee"]
    assert Decimal(str(fee["amount"])) == Decimal("18000.00")
    assert fee["isActive"] is True
    # Exactly one active fee remains.
    assert admission.fees.filter(is_active=True).count() == 1


def test_admin_view_only_cannot_change_fee(admin_client, admission):
    result = admin_client.execute(CHANGE_FEE, _vars(admission))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    # Unchanged: still the initial 15000 fee.
    assert admission.active_fee.amount == Decimal("15000.00")


def test_nurse_fully_rejected_on_change_fee(nurse_client, admission):
    result = nurse_client.execute(CHANGE_FEE, _vars(admission))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_change_fee_surfaces_domain_error(finance_client, admission):
    admission.status = AdmissionStatus.DISCHARGED
    admission.save(update_fields=["status"])
    result = finance_client.execute(CHANGE_FEE, _vars(admission))
    assert result["data"] is None
    assert "discharged" in result["errors"][0]["message"]


# ------------------------------------------------------------- feeHistory (RBAC)
def test_fee_history_admin_and_finance_can_view(admin_client, finance_client, admission):
    pid = str(admission.patient_id)
    assert admin_client.execute(FEE_HISTORY, {"patientId": pid}).get("errors") is None
    res = finance_client.execute(FEE_HISTORY, {"patientId": pid})
    assert res.get("errors") is None
    assert len(res["data"]["feeHistory"]) == 1


def test_fee_history_nurse_rejected(nurse_client, admission):
    result = nurse_client.execute(FEE_HISTORY, {"patientId": str(admission.patient_id)})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


# ---------------------------------------------------- invoice fee immutability
def test_changing_fee_after_generation_does_not_alter_invoice(admission, db):
    finance = User.objects.create_user(
        email="fin2@fee.test", password="x", role=UserRole.FINANCE
    )
    invoice = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )
    original_fee_id = invoice.fee_id
    original_base = invoice.base_fee
    assert original_base == Decimal("15000.00")

    # Change the fee AFTER the invoice exists.
    FeeService.change_fee(admission.id, Decimal("99999.00"), "big raise", finance)

    invoice.refresh_from_db()
    assert invoice.base_fee == original_base          # unchanged
    assert invoice.fee_id == original_fee_id          # still the old fee
    assert invoice.fee.amount == Decimal("15000.00")  # snapshot preserved


# ------------------------------------------------------- verify_fee_migration
def test_verify_command_passes_on_valid_data(admission):
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    out = StringIO()
    call_command("verify_fee_migration", stdout=out)
    assert "all invariants hold" in out.getvalue()


def test_verify_command_fails_on_two_active_fees(admission):
    # Create a second active fee -> violates "exactly one active per ACTIVE".
    Fee.objects.create(
        admission=admission, amount=Decimal("16000"), effective_from=date(2026, 2, 1),
        is_active=True, reason="bad",
    )
    with pytest.raises(CommandError, match="violation"):
        call_command("verify_fee_migration")
