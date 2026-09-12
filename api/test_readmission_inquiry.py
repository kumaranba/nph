"""Tests for bringing a discharged patient into the pipeline as a re-admission
lead (createReadmissionInquiry, PRO-only)."""
from datetime import date

import pytest

from api.models import (
    Admission, AdmissionStatus, Inquiry, InquiryStatus, InquirySource, Patient,
)

CREATE = """
mutation($pid: ID!, $note: String) {
  createReadmissionInquiry(patientId: $pid, note: $note) {
    id name phone source status notes
  }
}
"""


@pytest.fixture
def discharged(db):
    p = Patient.objects.create(
        name="Ravi", guardian_phone="9876543210", diagnosis="d",
        admitting_doctor="Dr",
    )
    Admission.objects.create(
        patient=p, admission_date=date(2026, 1, 1), monthly_fee=1,
        discharge_date=date(2026, 2, 1), status=AdmissionStatus.DISCHARGED,
    )
    return p


def test_pro_creates_readmission_lead(pro_client, discharged):
    result = pro_client.execute(CREATE, {"pid": str(discharged.id), "note": "  keen  "})
    assert result.get("errors") is None
    data = result["data"]["createReadmissionInquiry"]
    assert data["name"] == "Ravi"
    assert data["phone"] == "9876543210"        # from the patient
    assert data["source"] == "READMISSION"
    assert data["status"] == "NEW"              # starts in the pipeline
    assert "keen" in data["notes"] and discharged.patient_id in data["notes"]


def test_rejected_when_currently_admitted(pro_client, discharged):
    Admission.objects.create(
        patient=discharged, admission_date=date(2026, 3, 1), monthly_fee=1,
        status=AdmissionStatus.ACTIVE,
    )
    result = pro_client.execute(CREATE, {"pid": str(discharged.id)})
    assert result["errors"]
    assert "currently admitted" in result["errors"][0]["message"].lower()


def test_duplicate_open_readmission_blocked(pro_client, discharged):
    Inquiry.objects.create(
        name="Ravi", phone="9876543210", source=InquirySource.READMISSION,
        status=InquiryStatus.NEW,
    )
    result = pro_client.execute(CREATE, {"pid": str(discharged.id)})
    assert result["errors"]
    assert "already has an open" in result["errors"][0]["message"].lower()


def test_duplicate_check_ignores_closed_leads(pro_client, discharged):
    # A prior re-admission lead that already converted (or was lost) doesn't block.
    Inquiry.objects.create(
        name="Ravi", phone="9876543210", source=InquirySource.READMISSION,
        status=InquiryStatus.ADMITTED,
    )
    result = pro_client.execute(CREATE, {"pid": str(discharged.id)})
    assert result.get("errors") is None


def test_unknown_patient(pro_client, db):
    result = pro_client.execute(CREATE, {"pid": "999999"})
    assert result["errors"]


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_forbidden_for_non_pro(request, client_name, discharged):
    client = request.getfixturevalue(client_name)
    result = client.execute(CREATE, {"pid": str(discharged.id)})
    assert result["errors"]
    assert Inquiry.objects.count() == 0
