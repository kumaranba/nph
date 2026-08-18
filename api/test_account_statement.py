"""Tests for the account-statement query and its PDF endpoint."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from api.auth import create_access_token
from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Patient,
    PaymentAccount,
    User,
    UserRole,
)

STATEMENT = """
query Statement($pid: ID!, $from: Date, $to: Date) {
  accountStatement(patientId: $pid, dateFrom: $from, dateTo: $to) {
    patientName patientCode openingBalance closingBalance
    totalDebits totalCredits
    lines { date description debit credit balance }
  }
}
"""


@pytest.fixture
def ledger(db):
    patient = Patient.objects.create(
        name="Jane", diagnosis="d", admitting_doctor="Dr",
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
    )
    for as_of in (date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)):
        BillingService.generate_invoice_for_admission(admission.id, as_of=as_of)
    user = User.objects.create_user(
        email="s@nph.test", password="secret123", role=UserRole.FINANCE
    )
    nila = PaymentAccount.objects.get(name="Nila")
    BillingService.record_payment_for_admission(
        admission, Decimal("15000"), Decimal("0"), date(2026, 2, 20), user, account=nila
    )
    return patient, admission


def test_statement_all_dates(finance_client, ledger):
    patient, _ = ledger
    data = finance_client.execute(
        STATEMENT, {"pid": str(patient.id)}
    )["data"]["accountStatement"]
    assert Decimal(data["openingBalance"]) == Decimal("0")
    assert Decimal(data["totalDebits"]) == Decimal("30000")   # 3 x 10000
    assert Decimal(data["totalCredits"]) == Decimal("15000")
    assert Decimal(data["closingBalance"]) == Decimal("15000")
    # 3 invoices + 1 payment, invoice-before-payment on the same day ordering.
    assert len(data["lines"]) == 4
    assert data["lines"][0]["description"].startswith("Fee")


def test_statement_date_range_carries_opening_balance(finance_client, ledger):
    patient, _ = ledger
    data = finance_client.execute(
        STATEMENT, {"pid": str(patient.id), "from": "2026-02-01", "to": "2026-03-31"}
    )["data"]["accountStatement"]
    # Jan invoice (10000) is before the range → opening balance.
    assert Decimal(data["openingBalance"]) == Decimal("10000")
    # Feb + Mar invoices in range (20000) and the Feb payment (15000).
    assert Decimal(data["totalDebits"]) == Decimal("20000")
    assert Decimal(data["totalCredits"]) == Decimal("15000")
    assert Decimal(data["closingBalance"]) == Decimal("15000")
    assert len(data["lines"]) == 3


def test_advance_credit_shows_negative_balance(finance_client, db):
    patient = Patient.objects.create(
        name="Rich", diagnosis="d", admitting_doctor="Dr",
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
    )
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    user = User.objects.create_user(
        email="r@nph.test", password="secret123", role=UserRole.FINANCE
    )
    BillingService.record_payment_for_admission(
        admission, Decimal("30000"), Decimal("0"), date(2026, 1, 20), user
    )
    data = finance_client.execute(
        STATEMENT, {"pid": str(patient.id)}
    )["data"]["accountStatement"]
    # Billed 10000, received 30000 → 20000 in advance credit.
    assert Decimal(data["closingBalance"]) == Decimal("-20000")


def test_nurse_cannot_view_statement(nurse_client, ledger):
    patient, _ = ledger
    result = nurse_client.execute(STATEMENT, {"pid": str(patient.id)})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


# --- Statement PDF endpoint -------------------------------------------------

def _pdf(role, patient_id, qs=""):
    user = User.objects.create_user(
        email=f"{role}@pdf.test", password="secret123", role=role
    )
    return Client().get(
        f"/reports/statement/{patient_id}.pdf{qs}",
        HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}",
    )


def test_statement_pdf_requires_auth(db, ledger):
    patient, _ = ledger
    assert Client().get(f"/reports/statement/{patient.id}.pdf").status_code == 401


def test_statement_pdf_forbidden_for_nurse(ledger):
    patient, _ = ledger
    assert _pdf(UserRole.NURSE, patient.id).status_code == 403


def test_statement_pdf_unknown_patient_404(db):
    assert _pdf(UserRole.FINANCE, 999999).status_code == 404


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.FINANCE])
def test_statement_pdf_download(ledger, role):
    patient, _ = ledger
    resp = _pdf(role, patient.id, "?from=2026-01-01&to=2026-03-31")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
