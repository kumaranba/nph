"""Tests for the PRM activity timeline (R2).

RBAC: PRO logs notes and reads timelines; ADMIN reads; Finance/Nurse none.
Stage changes and follow-up completions are auto-logged; a lead's activity
merges onto the patient timeline after conversion.
"""
import pytest

from api.models import Activity, ActivityKind, FollowUp, Inquiry, Patient


ADD = """
mutation($type: ActivityKindEnum!, $body: String!, $iid: ID, $pid: ID) {
  addActivity(type: $type, body: $body, inquiryId: $iid, patientId: $pid) {
    id type body createdBy { email }
  }
}
"""

TIMELINE = """
query($iid: ID, $pid: ID) {
  activities(inquiryId: $iid, patientId: $pid) { id type body }
}
"""

UPDATE_STATUS = """
mutation($id: ID!, $status: InquiryStatusEnum!) {
  updateInquiryStatus(inquiryId: $id, status: $status) { id status }
}
"""

LINK = """
mutation($id: ID!, $pid: ID!) {
  linkInquiryToPatient(inquiryId: $id, patientId: $pid) { id status }
}
"""

MARK_DONE = "mutation($id: ID!) { markFollowUpDone(followUpId: $id) { id isDone } }"


@pytest.fixture
def inquiry(db):
    return Inquiry.objects.create(name="Ramesh", phone="911", source="PHONE")


@pytest.fixture
def patient(db):
    return Patient.objects.create(name="Ramesh", diagnosis="d", admitting_doctor="Dr")


# --- manual notes ---------------------------------------------------------

def test_pro_adds_note_to_lead(pro_client, inquiry):
    result = pro_client.execute(ADD, {
        "type": "NOTE", "body": "  called, will visit Sat  ", "iid": str(inquiry.id),
    })
    assert result.get("errors") is None
    data = result["data"]["addActivity"]
    assert data["type"] == "NOTE"
    assert data["body"] == "called, will visit Sat"     # trimmed
    assert data["createdBy"]["email"] == "pro@nph.test"


def test_add_note_requires_a_subject(pro_client):
    result = pro_client.execute(ADD, {"type": "NOTE", "body": "orphan"})
    assert result["errors"]
    assert Activity.objects.count() == 0


def test_add_note_rejects_empty_body(pro_client, inquiry):
    result = pro_client.execute(ADD, {"type": "CALL", "body": "  ", "iid": str(inquiry.id)})
    assert result["errors"]


def test_lead_timeline_newest_first(pro_client, inquiry):
    pro_client.execute(ADD, {"type": "NOTE", "body": "first", "iid": str(inquiry.id)})
    pro_client.execute(ADD, {"type": "CALL", "body": "second", "iid": str(inquiry.id)})
    result = pro_client.execute(TIMELINE, {"iid": str(inquiry.id)})
    bodies = [a["body"] for a in result["data"]["activities"]]
    assert bodies == ["second", "first"]


# --- auto-logging ---------------------------------------------------------

def test_stage_change_is_logged(pro_client, inquiry):
    pro_client.execute(UPDATE_STATUS, {"id": str(inquiry.id), "status": "CONTACTED"})
    kinds = list(inquiry.activities.values_list("type", "body"))
    assert any(k == ActivityKind.STAGE_CHANGE and "Contacted" in b for k, b in kinds)


def test_conversion_merges_lead_activity_onto_patient(pro_client, inquiry, patient):
    # A note on the lead, then convert.
    pro_client.execute(ADD, {"type": "NOTE", "body": "pre-convert note", "iid": str(inquiry.id)})
    pro_client.execute(LINK, {"id": str(inquiry.id), "pid": str(patient.id)})

    # The patient timeline includes the lead's pre-conversion note + the
    # conversion stage-change.
    result = pro_client.execute(TIMELINE, {"pid": str(patient.id)})
    bodies = [a["body"] for a in result["data"]["activities"]]
    assert "pre-convert note" in bodies
    assert any("Admitted" in b for b in bodies)


def test_follow_up_completion_is_logged(pro_client, patient):
    fu = FollowUp.objects.create(patient=patient, note="review", follow_up_date="2026-01-01")
    pro_client.execute(MARK_DONE, {"id": str(fu.id)})
    logs = patient.activities.filter(type=ActivityKind.FOLLOW_UP)
    assert logs.count() == 1
    assert "review" in logs.first().body


# --- RBAC -----------------------------------------------------------------

def test_admin_can_read_but_not_add(admin_client, inquiry):
    Activity.objects.create(inquiry=inquiry, type=ActivityKind.NOTE, body="x")
    read = admin_client.execute(TIMELINE, {"iid": str(inquiry.id)})
    assert read.get("errors") is None
    assert len(read["data"]["activities"]) == 1

    write = admin_client.execute(ADD, {"type": "NOTE", "body": "no", "iid": str(inquiry.id)})
    assert write["errors"]


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_timeline_forbidden(request, client_name, inquiry):
    client = request.getfixturevalue(client_name)
    result = client.execute(TIMELINE, {"iid": str(inquiry.id)})
    assert result["errors"]
    assert result["data"] is None or result["data"]["activities"] is None
