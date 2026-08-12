"""Tests for the ``createAdmission`` mutation.

Covers the happy path (new patient + admission, bed flipped to OCCUPIED,
auto-generated patient_id), rejection of a bed that is already occupied,
the GraphQL-level rejection of a missing required field, and the ADMIN-only
role restriction.
"""
import re

import pytest

from api.models import Admission, Bed, BedStatus, Patient, Room

CREATE_ADMISSION = """
mutation Create($input: CreateAdmissionInput!) {
  createAdmission(input: $input) {
    id
    status
    admissionDate
    monthlyFee
    patient { patientId name age gender admittingDoctor }
    bed { id label status }
  }
}
"""


@pytest.fixture
def vacant_bed(db):
    room = Room.objects.create(name="Test Ward", capacity=2)
    return Bed.objects.create(room=room, label="T1", status=BedStatus.VACANT)


def _input(bed, **overrides):
    """Build a valid CreateAdmissionInput dict, with optional overrides."""
    data = {
        "name": "Jane Doe",
        "age": 72,
        "diagnosis": "Community-acquired pneumonia",
        "admittingDoctor": "Dr. Smith",
        "bedId": str(bed.id),
        "admissionDate": "2026-06-01",
        "monthlyFee": "25000.00",
        "guardianName": "John Doe",
        "guardianPhone": "9876543210",
    }
    data.update(overrides)
    return data


def test_admin_can_create_admission(admin_client, vacant_bed):
    result = admin_client.execute(CREATE_ADMISSION, {"input": _input(vacant_bed)})

    assert result.get("errors") is None
    adm = result["data"]["createAdmission"]
    assert adm["status"] == "ACTIVE"
    assert adm["bed"]["status"] == "OCCUPIED"

    # patient_id is auto-generated in the NPH-YYYY-NNNN format.
    assert re.match(r"^NPH-\d{4}-\d{4}$", adm["patient"]["patientId"])
    assert adm["patient"]["name"] == "Jane Doe"

    # The bed was really flipped in the database, and exactly one patient and
    # one admission now exist.
    vacant_bed.refresh_from_db()
    assert vacant_bed.status == BedStatus.OCCUPIED
    assert Patient.objects.count() == 1
    assert Admission.objects.count() == 1


def test_gender_is_stored_when_provided(admin_client, vacant_bed):
    result = admin_client.execute(
        CREATE_ADMISSION, {"input": _input(vacant_bed, gender="FEMALE")}
    )
    assert result.get("errors") is None
    assert result["data"]["createAdmission"]["patient"]["gender"] == "FEMALE"
    assert Patient.objects.get().gender == "FEMALE"


def test_gender_is_optional_and_defaults_blank(admin_client, vacant_bed):
    result = admin_client.execute(CREATE_ADMISSION, {"input": _input(vacant_bed)})
    assert result.get("errors") is None
    assert result["data"]["createAdmission"]["patient"]["gender"] == ""
    assert Patient.objects.get().gender == ""


def test_duplicate_bed_is_rejected(admin_client, vacant_bed):
    first = admin_client.execute(CREATE_ADMISSION, {"input": _input(vacant_bed)})
    assert first.get("errors") is None

    # Trying to admit a second patient into the now-occupied bed must fail.
    second = admin_client.execute(
        CREATE_ADMISSION, {"input": _input(vacant_bed, name="Second Patient")}
    )
    # createAdmission is a non-null field, so the resolver error nullifies
    # the whole `data` payload.
    assert second["data"] is None
    assert "already occupied" in second["errors"][0]["message"].lower()

    # The rejected attempt left no orphan patient and no second admission.
    assert Admission.objects.filter(bed=vacant_bed).count() == 1
    assert Patient.objects.count() == 1


def test_missing_required_field_is_rejected(admin_client, vacant_bed):
    payload = _input(vacant_bed)
    del payload["name"]  # `name` is a non-null field on the input type.

    result = admin_client.execute(CREATE_ADMISSION, {"input": payload})

    # GraphQL schema validation rejects the request before the resolver runs.
    assert result.get("errors") is not None
    assert "name" in result["errors"][0]["message"]
    # Nothing was created.
    assert Admission.objects.count() == 0
    assert Patient.objects.count() == 0


VACANT_BEDS = '{ beds(status: "VACANT") { id label status } }'


def test_vacant_beds_filter_excludes_occupied(admin_client, vacant_bed):
    # Admit a patient, occupying `vacant_bed`, then add a second vacant bed.
    admin_client.execute(CREATE_ADMISSION, {"input": _input(vacant_bed)})
    Bed.objects.create(
        room=vacant_bed.room, label="T2", status=BedStatus.VACANT
    )

    result = admin_client.execute(VACANT_BEDS)
    assert result.get("errors") is None
    labels = {b["label"] for b in result["data"]["beds"]}
    assert labels == {"T2"}  # the now-occupied T1 is excluded
    assert all(b["status"] == "VACANT" for b in result["data"]["beds"])


def test_non_admin_cannot_create_admission(nurse_client, vacant_bed):
    result = nurse_client.execute(CREATE_ADMISSION, {"input": _input(vacant_bed)})

    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]

    # The bed stays vacant and nothing is persisted.
    vacant_bed.refresh_from_db()
    assert vacant_bed.status == BedStatus.VACANT
    assert Admission.objects.count() == 0
    assert Patient.objects.count() == 0
