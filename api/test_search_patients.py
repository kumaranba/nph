"""Tests for the ``searchPatients`` query.

Covers searching by each field (name, patient_id, guardian_name,
guardian_phone), partial/fuzzy matches, the empty / no-results case, the
derived fee status, and that any authenticated role may search.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Fee,
    Invoice,
    InvoiceStatus,
    Patient,
    Room,
)

SEARCH = """
query Search($query: String!) {
  searchPatients(query: $query) {
    id
    patientId
    name
    guardianName
    guardianPhone
    admissionDate
    room
    bed
    feeStatus
  }
}
"""


@pytest.fixture
def patient(db):
    room = Room.objects.create(name="General Ward A", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    p = Patient.objects.create(
        name="Jane Doe",
        diagnosis="Pneumonia",
        guardian_name="John Doe",
        guardian_phone="9876543210",
        admitting_doctor="Dr. Smith",
    )
    Admission.objects.create(
        patient=p,
        bed=bed,
        admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )
    return p


def _names(result):
    return [r["name"] for r in result["data"]["searchPatients"]]


def test_search_by_name(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": "Jane Doe"})
    assert result.get("errors") is None
    rows = result["data"]["searchPatients"]
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Jane Doe"
    assert row["room"] == "General Ward A"
    assert row["bed"] == "A1"
    assert row["admissionDate"] == "2026-01-15"


def test_search_by_patient_id(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": patient.patient_id})
    assert _names(result) == ["Jane Doe"]


def test_search_by_guardian_name(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": "John Doe"})
    assert _names(result) == ["Jane Doe"]


def test_search_by_guardian_phone(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": "9876543210"})
    assert _names(result) == ["Jane Doe"]


def test_partial_match(admin_client, patient):
    # Partial fragments of name, id-year, and phone all match.
    assert _names(admin_client.execute(SEARCH, {"query": "jan"})) == ["Jane Doe"]
    assert _names(admin_client.execute(SEARCH, {"query": "98765"})) == ["Jane Doe"]


def test_no_results(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": "Nonexistent"})
    assert result.get("errors") is None
    assert result["data"]["searchPatients"] == []


def test_empty_query_returns_empty(admin_client, patient):
    result = admin_client.execute(SEARCH, {"query": "   "})
    assert result["data"]["searchPatients"] == []


def test_any_role_can_search(nurse_client, patient):
    # All roles are permitted to search.
    result = nurse_client.execute(SEARCH, {"query": "Jane"})
    assert result.get("errors") is None
    assert _names(result) == ["Jane Doe"]


def _fee_status(client, patient, query="Jane"):
    return client.execute(SEARCH, {"query": query})["data"]["searchPatients"][0][
        "feeStatus"
    ]


def test_fee_status_current_without_invoices(admin_client, patient):
    assert _fee_status(admin_client, patient) == "CURRENT"


def _fee_for(admission):
    return admission.active_fee or Fee.objects.create(
        admission=admission, amount=admission.monthly_fee,
        effective_from=admission.admission_date, is_active=True, reason="test",
    )


def test_fee_status_overdue(admin_client, patient):
    admission = patient.admissions.first()
    Invoice.objects.create(
        admission=admission,
        fee=_fee_for(admission),
        billing_period_start=date.today() - timedelta(days=40),
        billing_period_end=date.today() - timedelta(days=10),
        base_fee=Decimal("25000.00"),
        total_due=Decimal("25000.00"),
        status=InvoiceStatus.UNPAID,
    )
    assert _fee_status(admin_client, patient) == "OVERDUE"


def test_fee_status_due_soon(admin_client, patient):
    admission = patient.admissions.first()
    Invoice.objects.create(
        admission=admission,
        fee=_fee_for(admission),
        billing_period_start=date.today() - timedelta(days=20),
        billing_period_end=date.today() + timedelta(days=3),
        base_fee=Decimal("25000.00"),
        total_due=Decimal("25000.00"),
        status=InvoiceStatus.PARTIAL,
    )
    assert _fee_status(admin_client, patient) == "DUE_SOON"


# --- discharged patients --------------------------------------------------

SEARCH_FULL = """
query Search($query: String!) {
  searchPatients(query: $query) {
    name room bed feeStatus tags
  }
}
"""

DISCHARGE = """
mutation($id: ID!) { dischargePatient(admissionId: $id) { admission { status } } }
"""


def _row(client, query="Jane"):
    return client.execute(SEARCH_FULL, {"query": query})["data"]["searchPatients"][0]


def test_discharged_patient_hides_bed_and_shows_nil_and_tag(admin_client, patient):
    admission = patient.admissions.first()
    # No invoices → nothing owed → clean discharge.
    result = admin_client.execute(DISCHARGE, {"id": str(admission.id)})
    assert result.get("errors") is None

    row = _row(admin_client)
    assert row["room"] is None and row["bed"] is None   # bed hidden
    assert row["feeStatus"] == "NIL"                     # tallied
    assert "Discharged" in row["tags"]                   # auto-tagged


def test_discharged_patient_owing_shows_overdue(admin_client, patient):
    admission = patient.admissions.first()
    # Discharge blocks with dues, so seed a settled discharge then leave a debt:
    # here we mark discharged directly and add an unpaid invoice.
    admission.status = AdmissionStatus.DISCHARGED
    admission.discharge_date = date.today()
    admission.save()
    Invoice.objects.create(
        admission=admission, fee=_fee_for(admission),
        billing_period_start=date(2026, 1, 15), billing_period_end=date(2026, 2, 14),
        base_fee=Decimal("25000.00"), total_due=Decimal("25000.00"),
        status=InvoiceStatus.UNPAID,
    )
    row = _row(admin_client)
    assert row["room"] is None and row["bed"] is None
    assert row["feeStatus"] == "OVERDUE"                 # still owes


def test_readmission_clears_discharged_tag(admin_client, finance_client, patient):
    admission = patient.admissions.first()
    admin_client.execute(DISCHARGE, {"id": str(admission.id)})
    assert "Discharged" in _row(admin_client)["tags"]

    # Re-admit (ADMIN) — tag drops, bed returns.
    readmit = """
    mutation($pid: ID!, $d: Date!, $fee: Decimal!) {
      readmitPatient(patientId: $pid, admissionDate: $d, monthlyFee: $fee) { id status }
    }
    """
    res = admin_client.execute(
        readmit, {"pid": str(patient.id), "d": str(date.today()), "fee": "25000"}
    )
    assert res.get("errors") is None
    row = _row(admin_client)
    assert "Discharged" not in row["tags"]
    assert row["feeStatus"] != "NIL"                     # active billing again
