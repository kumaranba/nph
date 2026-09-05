"""Tests for the patient alternate_id — editable, unique, searchable."""
import pytest

from api.models import Patient

UPDATE = """
mutation($id: ID!, $input: UpdatePatientInput!) {
  updatePatient(patientId: $id, input: $input) { id alternateId }
}
"""

SEARCH = """
query($q: String!) { searchPatients(query: $q) { id name } }
"""


@pytest.fixture
def patient(db):
    return Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")


def test_admin_sets_alternate_id(admin_client, patient):
    result = admin_client.execute(UPDATE, {
        "id": str(patient.id), "input": {"alternateId": "  OLD-123 "},
    })
    assert result.get("errors") is None
    assert result["data"]["updatePatient"]["alternateId"] == "OLD-123"   # trimmed
    patient.refresh_from_db()
    assert patient.alternate_id == "OLD-123"


def test_clearing_stores_null_and_allows_multiple(admin_client, patient):
    other = Patient.objects.create(name="Sam", diagnosis="d", admitting_doctor="Dr")
    # Both cleared → both NULL, no unique clash.
    for p in (patient, other):
        r = admin_client.execute(UPDATE, {"id": str(p.id), "input": {"alternateId": ""}})
        assert r.get("errors") is None
    patient.refresh_from_db(); other.refresh_from_db()
    assert patient.alternate_id is None and other.alternate_id is None


def test_duplicate_alternate_id_rejected(admin_client, patient):
    Patient.objects.create(
        name="Sam", diagnosis="d", admitting_doctor="Dr", alternate_id="DUP-1",
    )
    result = admin_client.execute(UPDATE, {
        "id": str(patient.id), "input": {"alternateId": "DUP-1"},
    })
    assert result["errors"]
    assert "already in use" in result["errors"][0]["message"].lower()
    patient.refresh_from_db()
    assert patient.alternate_id is None


def test_search_matches_alternate_id(admin_client, patient):
    patient.alternate_id = "REG-9988"
    patient.save(update_fields=["alternate_id"])
    result = admin_client.execute(SEARCH, {"q": "REG-9988"})
    assert result.get("errors") is None
    ids = [r["id"] for r in result["data"]["searchPatients"]]
    assert str(patient.id) in ids


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "pro_client"])
def test_only_admin_edits_alternate_id(request, client_name, patient):
    client = request.getfixturevalue(client_name)
    result = client.execute(UPDATE, {
        "id": str(patient.id), "input": {"alternateId": "X-1"},
    })
    assert result["errors"]
    patient.refresh_from_db()
    assert patient.alternate_id is None
