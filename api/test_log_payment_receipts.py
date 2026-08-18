"""Every human-recorded payment gets a receipt, so it shows in payments
history and counts on the account statement — including the invoice-level
'log payment' flow, and existing payments via the backfill migration."""
from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps

from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Invoice,
    Patient,
    Payment,
    PaymentAccount,
    PaymentReceipt,
    User,
    UserRole,
)

LOG_PAYMENT = """
mutation Log($invoiceId: ID!, $amount: Decimal!, $paidOn: Date!, $accountId: ID) {
  logPayment(invoiceId: $invoiceId, amount: $amount, paidOn: $paidOn, accountId: $accountId) {
    id status
  }
}
"""

RECEIPTS = "{ paymentReceipts { id amount account { name } } }"

STATEMENT = """
query($pid: ID!) {
  accountStatement(patientId: $pid) {
    totalCredits closingBalance
    lines { description credit }
  }
}
"""


@pytest.fixture
def invoice(db):
    patient = Patient.objects.create(
        name="Jane", age=60, diagnosis="d", admitting_doctor="Dr",
    )
    admission = Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
    )
    inv = BillingService.generate_invoice_for_admission(
        admission.id, as_of=date(2026, 1, 15)
    )
    return patient, admission, inv


def test_log_payment_creates_receipt_with_account(finance_client, invoice):
    patient, _, inv = invoice
    nila = PaymentAccount.objects.get(name="Nila")
    result = finance_client.execute(LOG_PAYMENT, {
        "invoiceId": str(inv.id), "amount": "10000",
        "paidOn": "2026-01-20", "accountId": str(nila.id),
    })
    assert result.get("errors") is None

    receipt = PaymentReceipt.objects.get()
    assert receipt.amount == Decimal("10000")
    assert receipt.account == nila
    assert receipt.payments.count() == 1

    # Shows in payments history now.
    rows = finance_client.execute(RECEIPTS)["data"]["paymentReceipts"]
    assert len(rows) == 1
    assert rows[0]["account"]["name"] == "Nila"


def test_log_payment_counts_as_statement_credit(finance_client, invoice):
    patient, _, inv = invoice
    finance_client.execute(LOG_PAYMENT, {
        "invoiceId": str(inv.id), "amount": "10000",
        "paidOn": "2026-01-20", "accountId": None,
    })
    data = finance_client.execute(
        STATEMENT, {"pid": str(patient.id)}
    )["data"]["accountStatement"]
    assert Decimal(data["totalCredits"]) == Decimal("10000")
    assert Decimal(data["closingBalance"]) == Decimal("0")  # billed 10000, paid 10000
    assert any(ln["description"] == "Payment" for ln in data["lines"])


def test_backfill_creates_receipts_for_orphan_payments(finance_client, invoice):
    patient, _, inv = invoice
    user = User.objects.create_user(
        email="old@nph.test", password="secret123", role=UserRole.FINANCE
    )
    # A legacy receiptless payment (as old log_payment produced), plus a
    # credit-funded one (no recorder) that must stay receiptless.
    orphan = Payment.objects.create(
        invoice=inv, amount=Decimal("6000"), paid_on=date(2026, 1, 20),
        recorded_by=user,
    )
    credit = Payment.objects.create(
        invoice=inv, amount=Decimal("1000"), paid_on=date(2026, 1, 21),
        recorded_by=None,
    )
    assert PaymentReceipt.objects.count() == 0

    mod = import_module("api.migrations.0016_backfill_payment_receipts")
    mod.backfill(django_apps, None)

    orphan.refresh_from_db()
    credit.refresh_from_db()
    assert orphan.receipt is not None
    assert orphan.receipt.amount == Decimal("6000")
    assert credit.receipt is None  # credit draw-down stays receiptless

    rows = finance_client.execute(RECEIPTS)["data"]["paymentReceipts"]
    assert len(rows) == 1
