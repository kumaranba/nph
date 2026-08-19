"""Tests for the PRM follow-up API — create / mark-done / due list + RBAC.

RBAC contract mirrors inquiries: PRO manages follow-ups fully; ADMIN is
view-only (may read `followUps` / `dueFollowUps` but not write); FINANCE and
NURSE have no access.
"""
from datetime import date, timedelta

import pytest

from api.models import Admission, FollowUp, Patient


CREATE = """
mutation($data: CreateFollowUpInput!) {
  createFollowUp(data: $data) {
    id note followUpDate isDone
    patient { id } admission { id } createdBy { email }
  }
}
"""

FOLLOW_UPS = """
query($pid: ID!) {
  followUps(patientId: $pid) { id note followUpDate isDone }
}
"""

DUE = """
query { dueFollowUps { id note followUpDate patient { id name } } }
"""

DUE_COUNT = """
query { dueFollowUpCount }
"""

MARK_DONE = """
mutation($id: ID!) {
  markFollowUpDone(followUpId: $id) { id isDone }
}
"""


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        name="Ramesh", diagnosis="d", admitting_doctor="Dr"
    )


@pytest.fixture
def follow_up(patient):
    return FollowUp.objects.create(
        patient=patient, note="call guardian",
        follow_up_date=date.today() - timedelta(days=1),
    )


# --- create ---------------------------------------------------------------

def test_pro_creates_follow_up(pro_client, patient):
    result = pro_client.execute(CREATE, {"data": {
        "patientId": str(patient.id),
        "followUpDate": str(date.today() + timedelta(days=3)),
        "note": "  ring back  ",
    }})
    assert result.get("errors") is None
    data = result["data"]["createFollowUp"]
    assert data["note"] == "ring back"      # trimmed
    assert data["isDone"] is False
    assert data["patient"]["id"] == str(patient.id)
    assert data["admission"] is None
    assert data["createdBy"]["email"] == "pro@nph.test"
    assert FollowUp.objects.count() == 1


def test_create_follow_up_with_admission(pro_client, patient):
    adm = Admission.objects.create(patient=patient, admission_date=date.today(), monthly_fee=1000)
    result = pro_client.execute(CREATE, {"data": {
        "patientId": str(patient.id),
        "admissionId": str(adm.id),
        "followUpDate": str(date.today()),
    }})
    assert result.get("errors") is None
    assert result["data"]["createFollowUp"]["admission"]["id"] == str(adm.id)


def test_create_follow_up_unknown_patient(pro_client):
    result = pro_client.execute(CREATE, {"data": {
        "patientId": "999999", "followUpDate": str(date.today()),
    }})
    assert result["errors"]
    assert FollowUp.objects.count() == 0


def test_create_follow_up_admission_of_other_patient(pro_client, patient):
    other = Patient.objects.create(name="X", diagnosis="d", admitting_doctor="Dr")
    adm = Admission.objects.create(patient=other, admission_date=date.today(), monthly_fee=1000)
    result = pro_client.execute(CREATE, {"data": {
        "patientId": str(patient.id),
        "admissionId": str(adm.id),
        "followUpDate": str(date.today()),
    }})
    assert result["errors"]
    assert FollowUp.objects.count() == 0


# --- per-patient list -----------------------------------------------------

def test_follow_ups_for_patient_sorted(pro_client, patient):
    FollowUp.objects.create(patient=patient, follow_up_date=date(2026, 3, 1))
    FollowUp.objects.create(patient=patient, follow_up_date=date(2026, 1, 1))
    other = Patient.objects.create(name="Y", diagnosis="d", admitting_doctor="Dr")
    FollowUp.objects.create(patient=other, follow_up_date=date(2026, 2, 1))

    result = pro_client.execute(FOLLOW_UPS, {"pid": str(patient.id)})
    dates = [r["followUpDate"] for r in result["data"]["followUps"]]
    assert dates == ["2026-01-01", "2026-03-01"]      # this patient only, sorted


# --- due list / bell ------------------------------------------------------

def test_due_list_excludes_future_and_done(pro_client, patient):
    # due: on/before today and not done
    due = FollowUp.objects.create(
        patient=patient, follow_up_date=date.today() - timedelta(days=1)
    )
    FollowUp.objects.create(  # future — not due
        patient=patient, follow_up_date=date.today() + timedelta(days=5)
    )
    FollowUp.objects.create(  # past but done — not due
        patient=patient, follow_up_date=date.today() - timedelta(days=2),
        is_done=True,
    )
    result = pro_client.execute(DUE, {})
    ids = [r["id"] for r in result["data"]["dueFollowUps"]]
    assert ids == [str(due.id)]

    count = pro_client.execute(DUE_COUNT, {})
    assert count["data"]["dueFollowUpCount"] == 1


def test_today_is_due(pro_client, patient):
    FollowUp.objects.create(patient=patient, follow_up_date=date.today())
    result = pro_client.execute(DUE_COUNT, {})
    assert result["data"]["dueFollowUpCount"] == 1


# --- mark done ------------------------------------------------------------

def test_mark_done_clears_from_due(pro_client, follow_up):
    result = pro_client.execute(MARK_DONE, {"id": str(follow_up.id)})
    assert result.get("errors") is None
    assert result["data"]["markFollowUpDone"]["isDone"] is True
    follow_up.refresh_from_db()
    assert follow_up.is_done is True
    # gone from the due list
    assert pro_client.execute(DUE_COUNT, {})["data"]["dueFollowUpCount"] == 0


def test_mark_done_idempotent(pro_client, follow_up):
    pro_client.execute(MARK_DONE, {"id": str(follow_up.id)})
    result = pro_client.execute(MARK_DONE, {"id": str(follow_up.id)})
    assert result.get("errors") is None
    assert result["data"]["markFollowUpDone"]["isDone"] is True


# --- RBAC -----------------------------------------------------------------

def test_admin_can_view_due(admin_client, follow_up):
    result = admin_client.execute(DUE, {})
    assert result.get("errors") is None
    assert len(result["data"]["dueFollowUps"]) == 1


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_due_query_forbidden(request, client_name, follow_up):
    client = request.getfixturevalue(client_name)
    result = client.execute(DUE, {})
    assert result["errors"]
    assert result["data"] is None or result["data"]["dueFollowUps"] is None


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_create_follow_up_forbidden_for_non_pro(request, client_name, patient):
    client = request.getfixturevalue(client_name)
    result = client.execute(CREATE, {"data": {
        "patientId": str(patient.id), "followUpDate": str(date.today()),
    }})
    assert result["errors"]
    assert FollowUp.objects.count() == 0


def test_admin_cannot_mark_done(admin_client, follow_up):
    result = admin_client.execute(MARK_DONE, {"id": str(follow_up.id)})
    assert result["errors"]
    follow_up.refresh_from_db()
    assert follow_up.is_done is False
