"""Additional charges are billed immediately, reopen paid invoices, land on a
settlement invoice for opening-balance-covered periods, get swept at discharge,
and show as itemized debit lines on the account statement."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Invoice,
    InvoiceStatus,
    Patient,
    User,
    UserRole,
)

CREATE_CHARGE = """
mutation($aid: ID!, $cat: ChargeCategoryEnum!, $amt: Decimal!, $d: Date!, $desc: String) {
  createCharge(admissionId: $aid, category: $cat, amount: $amt, chargeDate: $d, description: $desc) { id }
}
"""
DELETE_CHARGE = "mutation($id: ID!) { deleteCharge(chargeId: $id) }"
DISCHARGE = "mutation($aid: ID!) { dischargePatient(admissionId: $aid) { hasOutstandingDues } }"
STATEMENT = """
query($pid: ID!) { accountStatement(patientId: $pid) {
  totalDebits closingBalance lines { description debit } } }
"""


def _admission(opening_as_of=None):
    patient = Patient.objects.create(
        name="Jane", age=60, diagnosis="d", admitting_doctor="Dr",
    )
    return Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
        opening_balance_as_of=opening_as_of,
    )


def test_charge_tops_up_existing_invoice(finance_client, db):
    a = _admission()
    inv = BillingService.generate_invoice_for_admission(a.id, as_of=date(2026, 1, 15))
    finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": "2026-01-20", "desc": "x",
    })
    inv.refresh_from_db()
    assert inv.total_due == Decimal("10500")
    assert inv.status == InvoiceStatus.UNPAID


def test_charge_reopens_paid_invoice(finance_client, db):
    a = _admission()
    inv = BillingService.generate_invoice_for_admission(a.id, as_of=date(2026, 1, 15))
    BillingService.record_payment_for_admission(
        a, Decimal("10000"), Decimal("0"), date(2026, 1, 16),
        User.objects.create_user(email="f@nph.test", password="secret123", role=UserRole.FINANCE),
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID

    finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": "2026-01-20", "desc": "",
    })
    inv.refresh_from_db()
    assert inv.total_due == Decimal("10500")
    assert inv.status == InvoiceStatus.PARTIAL
    assert BillingService.balance_due(inv) == Decimal("500")


def test_covered_period_charge_goes_to_settlement_invoice(finance_client, db):
    # Imported: opening balance as of 2026-08-12; a charge dated in July is in a
    # covered period, so it bills on a settlement invoice.
    a = _admission(opening_as_of=date(2026, 8, 12))
    finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "563", "d": "2026-07-03", "desc": "July drugs",
    })
    settlement = Invoice.objects.get(admission=a, is_settlement=True)
    assert settlement.base_fee == Decimal("0")
    assert settlement.total_due == Decimal("563")
    assert BillingService.total_pending_dues(a) == Decimal("563")


def test_charge_is_itemized_on_statement(finance_client, db):
    a = _admission()
    BillingService.generate_invoice_for_admission(a.id, as_of=date(2026, 1, 15))
    finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": "2026-01-20", "desc": "Antibiotics",
    })
    data = finance_client.execute(
        STATEMENT, {"pid": str(a.patient_id)}
    )["data"]["accountStatement"]
    descriptions = [ln["description"] for ln in data["lines"]]
    # Fee and the charge are separate debit lines.
    assert any(d.startswith("Fee") for d in descriptions)
    assert any("Drugs" in d and "Antibiotics" in d for d in descriptions)
    # Debits total fee + charge.
    assert Decimal(data["totalDebits"]) == Decimal("10500")


def test_discharge_sweeps_unbilled_charge(finance_client, db):
    a = _admission()
    BillingService.generate_invoice_for_admission(a.id, as_of=date(2026, 1, 15))  # 10000
    # A charge that never got billed (created directly, bypassing create_charge).
    AdditionalCharge.objects.create(
        admission=a, category="DRUGS", amount=Decimal("750"),
        charge_date=date(2026, 1, 20),
        recorded_by=User.objects.create_user(
            email="n@nph.test", password="secret123", role=UserRole.FINANCE),
    )
    assert BillingService.total_pending_dues(a) == Decimal("10000")  # charge not reflected

    finance_client.execute(DISCHARGE, {"aid": str(a.id)})
    assert BillingService.total_pending_dues(a) == Decimal("10750")  # swept in


def test_delete_charge_reverses_topup_and_blocks_when_paid(finance_client, db):
    a = _admission()
    inv = BillingService.generate_invoice_for_admission(a.id, as_of=date(2026, 1, 15))
    res = finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": "2026-01-20", "desc": "",
    })
    charge_id = res["data"]["createCharge"]["id"]
    inv.refresh_from_db()
    assert inv.total_due == Decimal("10500")

    finance_client.execute(DELETE_CHARGE, {"id": charge_id})
    inv.refresh_from_db()
    assert inv.total_due == Decimal("10000")

    # Now pay the invoice, add + can't delete a charge on a paid invoice.
    BillingService.record_payment_for_admission(
        a, Decimal("10000"), Decimal("0"), date(2026, 1, 16),
        User.objects.create_user(email="p@nph.test", password="secret123", role=UserRole.FINANCE),
    )
    r2 = finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": "2026-01-20", "desc": "",
    })  # reopens to PARTIAL
    # Pay the remaining 500 so the invoice is PAID again.
    inv.refresh_from_db()
    BillingService.record_payment_for_admission(
        a, Decimal("500"), Decimal("0"), date(2026, 1, 17),
        User.objects.get(email="p@nph.test"),
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID
    blocked = finance_client.execute(
        DELETE_CHARGE, {"id": r2["data"]["createCharge"]["id"]})
    assert "already paid" in blocked["errors"][0]["message"].lower()


def test_future_charge_date_rejected(finance_client, db):
    a = _admission()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = finance_client.execute(CREATE_CHARGE, {
        "aid": str(a.id), "cat": "DRUGS", "amt": "500", "d": tomorrow, "desc": "",
    })
    assert "future" in res["errors"][0]["message"].lower()


def test_bill_pending_charges_command_sweeps_stranded(db):
    from django.core.management import call_command
    from io import StringIO

    a = _admission(opening_as_of=date(2026, 8, 12))
    AdditionalCharge.objects.create(
        admission=a, category="DRUGS", amount=Decimal("563"),
        charge_date=date(2026, 7, 3),
        recorded_by=User.objects.create_user(
            email="o@nph.test", password="secret123", role=UserRole.FINANCE),
    )
    assert BillingService.total_pending_dues(a) == Decimal("0")

    call_command("bill_pending_charges", stdout=StringIO())
    assert BillingService.total_pending_dues(a) == Decimal("563")
    assert Invoice.objects.filter(admission=a, is_settlement=True).exists()
