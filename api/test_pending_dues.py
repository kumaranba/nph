"""Tests for the pending-dues list (past dues) and the fees-due PDF report."""
import io
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from api.auth import create_access_token
from api.billing import BillingService
from api.models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Gender,
    Patient,
    User,
    UserRole,
)

PENDING_DUES = """
{
  pendingDuesList {
    name gender place contact
    admissionDate currentFees totalPendingDues
  }
}
"""

AS_OF = date(2026, 8, 12)


def _patient_with_dues(
    name, gender, monthly, opening,
    place="Town", contact="999", status=AdmissionStatus.ACTIVE,
    admission_date=date(2025, 3, 3),
):
    patient = Patient.objects.create(
        name=name, age=40, gender=gender, diagnosis="d",
        admitting_doctor="Dr", place=place, guardian_phone=contact,
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=admission_date,
        monthly_fee=Decimal(monthly), status=status,
        opening_balance=Decimal(opening), opening_balance_as_of=AS_OF,
    )
    if Decimal(opening) > 0:
        BillingService.create_opening_balance_invoice(
            admission.id, Decimal(opening), as_of=AS_OF
        )
    return patient, admission


@pytest.fixture
def dues_dataset(db):
    _patient_with_dues("Manikandan", Gender.MALE, 9500, 13500, place="Trichy")
    _patient_with_dues("Ravi", Gender.FEMALE, 10500, 10500, place="Orathanadu")
    # Zero dues → excluded.
    _patient_with_dues("PaidUp", Gender.MALE, 9500, 0)
    # Discharged with dues → excluded (active admissions only).
    _patient_with_dues(
        "Gone", Gender.MALE, 9500, 5000, status=AdmissionStatus.DISCHARGED
    )


# --- pendingDuesList query --------------------------------------------------

def test_pending_dues_lists_active_debtors_highest_first(finance_client, dues_dataset):
    result = finance_client.execute(PENDING_DUES)
    assert result.get("errors") is None
    rows = result["data"]["pendingDuesList"]

    # Only the two active patients who owe money, sorted by dues desc.
    assert [r["name"] for r in rows] == ["Manikandan", "Ravi"]
    top = rows[0]
    assert top["gender"] == "MALE"
    assert top["place"] == "Trichy"
    assert top["contact"] == "999"
    assert Decimal(top["totalPendingDues"]) == Decimal("13500")
    # Current cycle charge is the monthly fee when there are no extra charges.
    assert Decimal(top["currentFees"]) == Decimal("9500")
    assert top["admissionDate"] == "2025-03-03"


def test_current_fees_includes_current_period_charges(finance_client, db):
    _, admission = _patient_with_dues("Withcharge", Gender.MALE, 9500, 13500)
    recorder = User.objects.create_user(
        email="r@nph.test", password="secret123", role=UserRole.FINANCE
    )
    # A charge dated inside the current (Aug) period lifts the current fees.
    AdditionalCharge.objects.create(
        admission=admission, category="DRUGS", amount=Decimal("500"),
        charge_date=date(2026, 8, 10), recorded_by=recorder,
    )
    rows = finance_client.execute(PENDING_DUES)["data"]["pendingDuesList"]
    row = next(r for r in rows if r["name"] == "Withcharge")
    assert Decimal(row["currentFees"]) == Decimal("10000")  # 9500 + 500


def test_nurse_cannot_access_pending_dues(nurse_client, dues_dataset):
    result = nurse_client.execute(PENDING_DUES)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


# --- fees-due PDF endpoint --------------------------------------------------

def _pdf_get(role):
    user = User.objects.create_user(
        email=f"{role}@pdf.test", password="secret123", role=role
    )
    return Client().get(
        "/reports/fees-due.pdf",
        HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}",
    )


def test_pdf_requires_authentication(db):
    resp = Client().get("/reports/fees-due.pdf")
    assert resp.status_code == 401


def test_pdf_forbidden_for_nurse(db, dues_dataset):
    resp = _pdf_get(UserRole.NURSE)
    assert resp.status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.FINANCE])
def test_pdf_download_for_admin_and_finance(db, dues_dataset, role):
    resp = _pdf_get(role)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp["Content-Disposition"] == 'attachment; filename="fees-due.pdf"'
    assert resp.content[:5] == b"%PDF-"
