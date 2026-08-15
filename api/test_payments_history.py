"""Tests for the payments-history query and the receipt PDF endpoint."""
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

RECEIPTS = """
query Receipts($from: Date, $to: Date) {
  paymentReceipts(dateFrom: $from, dateTo: $to) {
    id patientName patientCode paidOn amount feesAmount chargesAmount account { name }
  }
}
"""


@pytest.fixture
def receipts(db):
    patient = Patient.objects.create(
        name="Jane", age=60, diagnosis="d", admitting_doctor="Dr",
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("15000"), status=AdmissionStatus.ACTIVE,
    )
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 2, 15))
    user = User.objects.create_user(
        email="rec@nph.test", password="secret123", role=UserRole.FINANCE
    )
    nila = PaymentAccount.objects.get(name="Nila")
    # Two receipts on different dates.
    r1, *_ = BillingService.record_payment_for_admission(
        admission, Decimal("12000"), Decimal("3000"), date(2026, 1, 20), user, account=nila
    )
    r2, *_ = BillingService.record_payment_for_admission(
        admission, Decimal("15000"), Decimal("0"), date(2026, 2, 20), user, account=nila
    )
    return patient, r1, r2


def test_payment_receipts_lists_with_flattened_fields(finance_client, receipts):
    patient, r1, r2 = receipts
    result = finance_client.execute(RECEIPTS)
    assert result.get("errors") is None
    rows = result["data"]["paymentReceipts"]
    # Newest first.
    assert [int(r["id"]) for r in rows] == [r2.id, r1.id]
    top = rows[0]
    assert top["patientName"] == "Jane"
    assert top["patientCode"] == patient.patient_id
    assert Decimal(top["amount"]) == Decimal("15000")
    assert top["account"]["name"] == "Nila"


def test_payment_receipts_date_range_is_inclusive(finance_client, receipts):
    _, r1, _ = receipts
    result = finance_client.execute(
        RECEIPTS, {"from": "2026-01-01", "to": "2026-01-31"}
    )
    rows = result["data"]["paymentReceipts"]
    assert [int(r["id"]) for r in rows] == [r1.id]


def test_nurse_cannot_list_receipts(nurse_client, receipts):
    result = nurse_client.execute(RECEIPTS)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


# --- Receipt PDF endpoint ---------------------------------------------------

def _pdf(role, receipt_id):
    user = User.objects.create_user(
        email=f"{role}@pdf.test", password="secret123", role=role
    )
    return Client().get(
        f"/reports/receipt/{receipt_id}.pdf",
        HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}",
    )


def test_receipt_pdf_requires_auth(db, receipts):
    _, r1, _ = receipts
    assert Client().get(f"/reports/receipt/{r1.id}.pdf").status_code == 401


def test_receipt_pdf_forbidden_for_nurse(receipts):
    _, r1, _ = receipts
    assert _pdf(UserRole.NURSE, r1.id).status_code == 403


def test_receipt_pdf_unknown_returns_404(db):
    assert _pdf(UserRole.FINANCE, 999999).status_code == 404


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.FINANCE])
def test_receipt_pdf_download(receipts, role):
    _, r1, _ = receipts
    resp = _pdf(role, r1.id)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp["Content-Disposition"] == f'attachment; filename="receipt-{r1.id}.pdf"'
    assert resp.content[:5] == b"%PDF-"
