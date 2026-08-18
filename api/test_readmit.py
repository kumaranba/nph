"""Tests for readmitPatient — admitting an existing patient (new/re-admission)."""
from datetime import date
from decimal import Decimal

import pytest

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Fee,
    Patient,
    Room,
)

READMIT = """
mutation($pid: ID!, $date: Date!, $fee: Decimal!, $bed: ID) {
  readmitPatient(patientId: $pid, admissionDate: $date, monthlyFee: $fee, bedId: $bed) {
    id status monthlyFee patient { id }
  }
}
"""


@pytest.fixture
def discharged_patient(db):
    patient = Patient.objects.create(name="Jane", diagnosis="d", admitting_doctor="Dr")
    old = Admission.objects.create(
        patient=patient, admission_date=date(2025, 1, 10),
        monthly_fee=Decimal("8000"), status=AdmissionStatus.DISCHARGED,
        discharge_date=date(2025, 6, 1),
    )
    Fee.objects.create(
        admission=old, amount=Decimal("8000"), effective_from=date(2025, 1, 10),
        is_active=False, reason="Initial fee",
    )
    return patient, old


def test_readmit_creates_independent_active_admission(admin_client, discharged_patient):
    patient, old = discharged_patient
    result = admin_client.execute(READMIT, {
        "pid": str(patient.id), "date": "2026-08-15", "fee": "12000", "bed": None,
    })
    assert result.get("errors") is None
    data = result["data"]["readmitPatient"]
    assert data["status"] == "ACTIVE"
    assert Decimal(data["monthlyFee"]) == Decimal("12000")

    # A new admission with its own active Fee; the old admission + fee untouched.
    assert Admission.objects.filter(patient=patient).count() == 2
    new = Admission.objects.get(patient=patient, status=AdmissionStatus.ACTIVE)
    assert new.fees.filter(is_active=True).count() == 1
    assert new.fees.get(is_active=True).amount == Decimal("12000")
    old.refresh_from_db()
    assert old.fees.count() == 1  # prior fee history preserved


def test_readmit_bills_on_admission(admin_client, discharged_patient):
    patient, _ = discharged_patient
    admin_client.execute(READMIT, {
        "pid": str(patient.id), "date": "2026-08-15", "fee": "12000", "bed": None,
    })
    from api.billing import BillingService
    new = Admission.objects.get(patient=patient, status=AdmissionStatus.ACTIVE)
    assert BillingService.total_pending_dues(new) > 0


def test_readmit_blocked_when_active_admission_exists(admin_client, db):
    patient = Patient.objects.create(name="Al", diagnosis="d", admitting_doctor="Dr")
    Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("5000"), status=AdmissionStatus.ACTIVE,
    )
    result = admin_client.execute(READMIT, {
        "pid": str(patient.id), "date": "2026-08-15", "fee": "12000", "bed": None,
    })
    assert result["data"] is None
    assert "active admission" in result["errors"][0]["message"].lower()


def test_readmit_flips_bed(admin_client, discharged_patient):
    patient, _ = discharged_patient
    room = Room.objects.create(name="W", capacity=1)
    bed = Bed.objects.create(room=room, label="B1", status=BedStatus.VACANT)
    admin_client.execute(READMIT, {
        "pid": str(patient.id), "date": "2026-08-15", "fee": "12000", "bed": str(bed.id),
    })
    bed.refresh_from_db()
    assert bed.status == BedStatus.OCCUPIED


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client"])
def test_readmit_admin_only(request, client_name, discharged_patient):
    patient, _ = discharged_patient
    client = request.getfixturevalue(client_name)
    result = client.execute(READMIT, {
        "pid": str(patient.id), "date": "2026-08-15", "fee": "12000", "bed": None,
    })
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
