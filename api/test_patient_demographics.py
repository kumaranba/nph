"""Sprint 1 — patient demographics: computed age (retires stored age),
food preference / alive-expiry, and ADMIN-only Aadhar at the resolver level."""
from datetime import date

import pytest

from api.models import FoodPreference, Patient

PATIENT = """
query($pk: ID!) {
  patient(pk: $pk) {
    name age dateOfBirth foodPreference isAlive dateOfExpiry
  }
}
"""
AADHAR = "query($pk: ID!) { patient(pk: $pk) { name aadharNumber } }"


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        name="Jane", diagnosis="d", admitting_doctor="Dr",
        date_of_birth=date(2000, 6, 1), food_preference=FoodPreference.VEG,
        aadhar_number="123456789012",
    )


# --- computed age -----------------------------------------------------------

def test_age_computed_from_dob(db):
    p = Patient.objects.create(
        name="A", diagnosis="d", admitting_doctor="x",
        date_of_birth=date(2000, 1, 1),
    )
    today = date.today()
    expected = today.year - 2000 - ((today.month, today.day) < (1, 1))
    assert p.age == expected


def test_age_none_without_dob(db):
    p = Patient.objects.create(name="B", diagnosis="d", admitting_doctor="x")
    assert p.age is None


def test_age_and_demographics_via_graphql(admin_client, patient):
    data = admin_client.execute(PATIENT, {"pk": str(patient.id)})["data"]["patient"]
    assert data["age"] == date.today().year - 2000 - (
        (date.today().month, date.today().day) < (6, 1)
    )
    assert data["dateOfBirth"] == "2000-06-01"
    assert data["foodPreference"] == "VEG"
    assert data["isAlive"] is True
    assert data["dateOfExpiry"] is None


# --- Aadhar ADMIN-only RBAC (resolver-level) --------------------------------

def test_admin_can_read_aadhar(admin_client, patient):
    result = admin_client.execute(AADHAR, {"pk": str(patient.id)})
    assert result.get("errors") is None
    assert result["data"]["patient"]["aadharNumber"] == "123456789012"


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client"])
def test_non_admin_cannot_read_aadhar(request, client_name, patient):
    client = request.getfixturevalue(client_name)
    result = client.execute(AADHAR, {"pk": str(patient.id)})
    # A permission error surfaces (the field nulls out) — not silent empty data.
    assert result.get("errors")
    assert "Aadhar" in result["errors"][0]["message"]
    assert result["data"]["patient"]["aadharNumber"] is None


def test_non_admin_can_still_read_other_patient_fields(finance_client, patient):
    # Not requesting aadhar → no error, other fields resolve fine.
    result = finance_client.execute(PATIENT, {"pk": str(patient.id)})
    assert result.get("errors") is None
    assert result["data"]["patient"]["name"] == "Jane"
