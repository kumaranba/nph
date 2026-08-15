"""Tests for the updatePatient mutation (ADMIN-only profile editing)."""
import pytest

from api.models import Gender, Patient

UPDATE = """
mutation Update($patientId: ID!, $input: UpdatePatientInput!) {
  updatePatient(patientId: $patientId, input: $input) {
    id name age gender diagnosis admittingDoctor
    guardianName guardianPhone place
  }
}
"""


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        name="Jane Doe", age=72, gender=Gender.FEMALE, diagnosis="Pneumonia",
        admitting_doctor="Dr. X", guardian_name="John", guardian_phone="999",
        place="Trichy",
    )


def test_admin_updates_only_provided_fields(admin_client, patient):
    result = admin_client.execute(UPDATE, {
        "patientId": str(patient.id),
        "input": {"name": "Jane R. Doe", "place": "Chennai"},
    })
    assert result.get("errors") is None
    data = result["data"]["updatePatient"]
    assert data["name"] == "Jane R. Doe"
    assert data["place"] == "Chennai"
    # Untouched fields are unchanged.
    assert data["diagnosis"] == "Pneumonia"
    assert data["guardianPhone"] == "999"
    patient.refresh_from_db()
    assert patient.name == "Jane R. Doe"
    assert patient.place == "Chennai"


def test_age_and_gender_can_be_cleared(admin_client, patient):
    result = admin_client.execute(UPDATE, {
        "patientId": str(patient.id),
        "input": {"age": None, "gender": None},
    })
    assert result.get("errors") is None
    data = result["data"]["updatePatient"]
    assert data["age"] is None
    assert data["gender"] == ""
    patient.refresh_from_db()
    assert patient.age is None
    assert patient.gender == ""


def test_empty_name_is_rejected(admin_client, patient):
    result = admin_client.execute(UPDATE, {
        "patientId": str(patient.id),
        "input": {"name": "   "},
    })
    assert result["data"] is None
    assert "name cannot be empty" in result["errors"][0]["message"].lower()


def test_unknown_patient_is_rejected(admin_client, db):
    result = admin_client.execute(UPDATE, {
        "patientId": "999999", "input": {"name": "X"},
    })
    assert result["data"] is None
    assert "not found" in result["errors"][0]["message"].lower()


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client"])
def test_non_admin_cannot_edit(request, client_name, patient):
    client = request.getfixturevalue(client_name)
    result = client.execute(UPDATE, {
        "patientId": str(patient.id), "input": {"name": "X"},
    })
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    patient.refresh_from_db()
    assert patient.name == "Jane Doe"  # unchanged
