"""Tests for the admission-history fields on AdmissionType — effective_fee
(current active fee, or the last fee at discharge) and outstanding_due —
exercised through the patient GraphQL query.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import (
    Admission, AdmissionStatus, Fee, Invoice, InvoiceStatus, Patient,
)

QUERY = """
query($pk: ID!) {
  patient(pk: $pk) {
    admissions {
      status
      admissionDate
      dischargeDate
      effectiveFee { amount }
      outstandingDue
    }
  }
}
"""


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        name="Suresh", diagnosis="d", admitting_doctor="Dr",
    )


def _fee(adm, amount, eff, active):
    return Fee.objects.create(
        admission=adm, amount=Decimal(amount), effective_from=eff,
        is_active=active, reason="t",
    )


def _admissions(client, patient):
    result = client.execute(QUERY, {"pk": str(patient.id)})
    assert result.get("errors") is None
    return result["data"]["patient"]["admissions"]


def test_effective_fee_is_active_fee_while_admitted(admin_client, patient):
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 2, 6),
        monthly_fee=Decimal("15500"), status=AdmissionStatus.ACTIVE,
    )
    _fee(adm, "15500", date(2026, 2, 6), True)
    row = _admissions(admin_client, patient)[0]
    assert Decimal(row["effectiveFee"]["amount"]) == Decimal("15500")


def test_effective_fee_is_last_fee_after_discharge(admin_client, patient):
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2025, 6, 3),
        discharge_date=date(2025, 6, 26), monthly_fee=Decimal("11500"),
        status=AdmissionStatus.DISCHARGED,
    )
    _fee(adm, "11500", date(2025, 6, 3), False)     # original
    _fee(adm, "14500", date(2025, 6, 15), False)    # changed, in force at exit
    row = _admissions(admin_client, patient)[0]
    # No active fee (discharged) → the newest fee is the effective one.
    assert Decimal(row["effectiveFee"]["amount"]) == Decimal("14500")


def test_effective_fee_none_without_any_fee(admin_client, patient):
    Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("0"), status=AdmissionStatus.DISCHARGED,
        discharge_date=date(2026, 1, 5),
    )
    row = _admissions(admin_client, patient)[0]
    assert row["effectiveFee"] is None


def test_outstanding_due_sums_unpaid(admin_client, patient):
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 2, 6),
        monthly_fee=Decimal("15500"), status=AdmissionStatus.ACTIVE,
    )
    fee = _fee(adm, "15500", date(2026, 2, 6), True)
    Invoice.objects.create(
        admission=adm, fee=fee,
        billing_period_start=date(2026, 2, 6), billing_period_end=date(2026, 3, 5),
        base_fee=Decimal("2400"), total_due=Decimal("2400"),
        status=InvoiceStatus.UNPAID,
    )
    row = _admissions(admin_client, patient)[0]
    assert Decimal(row["outstandingDue"]) == Decimal("2400")


def test_outstanding_due_zero_when_settled(admin_client, patient):
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2025, 6, 3),
        discharge_date=date(2025, 6, 26), monthly_fee=Decimal("11500"),
        status=AdmissionStatus.DISCHARGED,
    )
    _fee(adm, "11500", date(2025, 6, 3), False)
    row = _admissions(admin_client, patient)[0]
    assert Decimal(row["outstandingDue"]) == Decimal("0")


# --- readable by any authenticated role (fees shown to all) -----------------

@pytest.mark.parametrize(
    "client_name", ["admin_client", "finance_client", "nurse_client", "pro_client"]
)
def test_admission_history_readable_by_all_roles(request, client_name, patient):
    adm = Admission.objects.create(
        patient=patient, admission_date=date(2026, 2, 6),
        monthly_fee=Decimal("15500"), status=AdmissionStatus.ACTIVE,
    )
    _fee(adm, "15500", date(2026, 2, 6), True)
    client = request.getfixturevalue(client_name)
    row = _admissions(client, patient)[0]
    assert Decimal(row["effectiveFee"]["amount"]) == Decimal("15500")
    assert Decimal(row["outstandingDue"]) == Decimal("0")
