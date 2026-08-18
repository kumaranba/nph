"""Tests for payment accounts + the fees/charges split on record payment."""
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Patient,
    PaymentAccount,
    PaymentReceipt,
)

RECORD = """
mutation Record(
  $patientId: ID!, $feesAmount: Decimal!, $chargesAmount: Decimal!,
  $paidOn: Date!, $accountId: ID
) {
  recordPatientPayment(
    patientId: $patientId, feesAmount: $feesAmount,
    chargesAmount: $chargesAmount, paidOn: $paidOn, accountId: $accountId
  ) {
    receiptId totalRecorded feesAmount chargesAmount account invoicesPaid
  }
}
"""

ACCOUNTS = "{ paymentAccounts { name isActive } }"


@pytest.fixture
def admission(db):
    patient = Patient.objects.create(
        name="Jane", diagnosis="d", admitting_doctor="Dr",
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("15000"), status=AdmissionStatus.ACTIVE,
    )
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    return patient, admission


def test_seeded_accounts_listed_for_finance(finance_client, db):
    result = finance_client.execute(ACCOUNTS)
    names = {a["name"] for a in result["data"]["paymentAccounts"]}
    assert names == {"Nila", "Vaigari", "Bank AC"}


def test_nurse_cannot_list_accounts(nurse_client, db):
    result = nurse_client.execute(ACCOUNTS)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_record_payment_captures_split_and_account(finance_client, admission):
    patient, adm = admission
    account = PaymentAccount.objects.get(name="Nila")
    result = finance_client.execute(RECORD, {
        "patientId": str(patient.id),
        "feesAmount": "12000",
        "chargesAmount": "3000",
        "paidOn": "2026-01-20",
        "accountId": str(account.id),
    })
    assert result.get("errors") is None
    data = result["data"]["recordPatientPayment"]
    assert Decimal(data["totalRecorded"]) == Decimal("15000")
    assert Decimal(data["feesAmount"]) == Decimal("12000")
    assert Decimal(data["chargesAmount"]) == Decimal("3000")
    assert data["account"] == "Nila"
    assert data["invoicesPaid"] == 1

    # A receipt groups the allocation, carrying the split + account.
    receipt = PaymentReceipt.objects.get(pk=data["receiptId"])
    assert receipt.amount == Decimal("15000")
    assert receipt.account == account
    assert receipt.payments.count() == 1
    assert receipt.payments.first().amount == Decimal("15000")


def test_admin_can_record_payment(admin_client, admission):
    patient, _ = admission
    result = admin_client.execute(RECORD, {
        "patientId": str(patient.id),
        "feesAmount": "15000",
        "chargesAmount": "0",
        "paidOn": "2026-01-20",
        "accountId": None,
    })
    assert result.get("errors") is None
    assert result["data"]["recordPatientPayment"]["account"] is None


def test_zero_total_is_rejected(finance_client, admission):
    patient, _ = admission
    result = finance_client.execute(RECORD, {
        "patientId": str(patient.id),
        "feesAmount": "0", "chargesAmount": "0",
        "paidOn": "2026-01-20", "accountId": None,
    })
    assert result["data"] is None
    assert "must be positive" in result["errors"][0]["message"]


def test_inactive_account_is_rejected(finance_client, admission):
    patient, _ = admission
    acct = PaymentAccount.objects.create(name="Closed", is_active=False)
    result = finance_client.execute(RECORD, {
        "patientId": str(patient.id),
        "feesAmount": "1000", "chargesAmount": "0",
        "paidOn": "2026-01-20", "accountId": str(acct.id),
    })
    assert result["data"] is None
    assert "account not found" in result["errors"][0]["message"].lower()
