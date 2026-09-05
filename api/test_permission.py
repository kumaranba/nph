"""Tests for patient permission (home leave without discharge).

Permission is a record only: the bed stays occupied, full fees still apply (no
billing hooks), and it never blocks discharge or fee changes. ADMIN records it.
"""
from datetime import date

import pytest

from api.models import (
    Admission, AdmissionStatus, Bed, BedStatus, Permission, Patient, Room,
)

START = """
mutation($id: ID!, $start: Date!, $exp: Date, $note: String) {
  startPermission(admissionId: $id, startDate: $start, expectedReturn: $exp, note: $note) {
    id startDate expectedReturn returnDate note isOut
    admission { id patient { name } }
  }
}
"""

END = """
mutation($id: ID!, $rd: Date) {
  endPermission(permissionId: $id, returnDate: $rd) { id returnDate isOut }
}
"""

ON_PERMISSION = "{ patientsOnPermission { id admission { patient { name } } } }"
HISTORY = 'query($id: ID!) { permissions(admissionId: $id) { id isOut } }'


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="MW1", capacity=2)
    bed = Bed.objects.create(room=room, label="B1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")
    return Admission.objects.create(
        patient=patient, bed=bed, admission_date=date(2026, 1, 1),
        monthly_fee=10000, status=AdmissionStatus.ACTIVE,
    )


# --- start ----------------------------------------------------------------

def test_admin_starts_permission(admin_client, admission):
    r = admin_client.execute(START, {
        "id": str(admission.id), "start": "2026-02-01",
        "exp": "2026-02-05", "note": "  family visit  ",
    })
    assert r.get("errors") is None
    data = r["data"]["startPermission"]
    assert data["isOut"] is True
    assert data["returnDate"] is None
    assert data["note"] == "family visit"
    # Bed is untouched — still theirs.
    admission.bed.refresh_from_db()
    assert admission.bed.status == BedStatus.OCCUPIED


def test_cannot_start_second_open_permission(admin_client, admission):
    Permission.objects.create(admission=admission, start_date=date(2026, 2, 1))
    r = admin_client.execute(START, {"id": str(admission.id), "start": "2026-02-03"})
    assert r["errors"]
    assert "already out" in r["errors"][0]["message"].lower()


def test_cannot_start_on_discharged_admission(admin_client, admission):
    admission.status = AdmissionStatus.DISCHARGED
    admission.save(update_fields=["status"])
    r = admin_client.execute(START, {"id": str(admission.id), "start": "2026-02-01"})
    assert r["errors"]


def test_expected_return_before_start_rejected(admin_client, admission):
    r = admin_client.execute(START, {
        "id": str(admission.id), "start": "2026-02-05", "exp": "2026-02-01",
    })
    assert r["errors"]


# --- end ------------------------------------------------------------------

def test_end_permission_marks_returned(admin_client, admission):
    p = Permission.objects.create(admission=admission, start_date=date(2026, 2, 1))
    r = admin_client.execute(END, {"id": str(p.id), "rd": "2026-02-04"})
    assert r.get("errors") is None
    assert r["data"]["endPermission"]["isOut"] is False
    p.refresh_from_db()
    assert p.return_date == date(2026, 2, 4)


def test_end_already_closed_rejected(admin_client, admission):
    p = Permission.objects.create(
        admission=admission, start_date=date(2026, 2, 1), return_date=date(2026, 2, 3)
    )
    r = admin_client.execute(END, {"id": str(p.id)})
    assert r["errors"]


def test_return_before_start_rejected(admin_client, admission):
    p = Permission.objects.create(admission=admission, start_date=date(2026, 2, 5))
    r = admin_client.execute(END, {"id": str(p.id), "rd": "2026-02-01"})
    assert r["errors"]


# --- queries --------------------------------------------------------------

def test_patients_on_permission_lists_only_open(admin_client, admission):
    other = Admission.objects.create(
        patient=Patient.objects.create(name="Sam", diagnosis="d", admitting_doctor="Dr"),
        admission_date=date(2026, 1, 1), monthly_fee=1, status=AdmissionStatus.ACTIVE,
    )
    Permission.objects.create(admission=admission, start_date=date(2026, 2, 1))  # out
    Permission.objects.create(
        admission=other, start_date=date(2026, 1, 5), return_date=date(2026, 1, 6)
    )  # returned
    r = admin_client.execute(ON_PERMISSION)
    names = [p["admission"]["patient"]["name"] for p in r["data"]["patientsOnPermission"]]
    assert names == ["Ravi"]


def test_permission_history_for_admission(admin_client, admission):
    Permission.objects.create(
        admission=admission, start_date=date(2026, 1, 5), return_date=date(2026, 1, 7)
    )
    Permission.objects.create(admission=admission, start_date=date(2026, 2, 1))
    r = admin_client.execute(HISTORY, {"id": str(admission.id)})
    assert len(r["data"]["permissions"]) == 2


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "pro_client"])
def test_start_permission_forbidden_for_non_admin(request, client_name, admission):
    client = request.getfixturevalue(client_name)
    r = client.execute(START, {"id": str(admission.id), "start": "2026-02-01"})
    assert r["errors"]
    assert Permission.objects.count() == 0
