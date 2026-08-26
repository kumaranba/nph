"""Tests for auto-scheduled follow-ups (R6): +30-day aftercare on discharge,
+3-day OP nudge on consult, the reconcile backfill, and lead follow-ups on the
due list."""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from api.models import (
    Admission,
    AdmissionStatus,
    FollowUp,
    FollowUpKind,
    Inquiry,
    Patient,
)


DISCHARGE = "mutation($id: ID!) { dischargePatient(admissionId: $id) { admission { status } } }"
SET_CONSULTED = "mutation($id: ID!, $d: Date) { setConsulted(inquiryId: $id, consultedOn: $d) { id } }"
CREATE = "mutation($data: CreateInquiryInput!) { createInquiry(data: $data) { id } }"
DUE = "query { dueFollowUps { id kind subjectName } }"
MARK_DONE = "mutation($id: ID!) { markFollowUpDone(followUpId: $id) { id isDone } }"


@pytest.fixture
def admission(db):
    patient = Patient.objects.create(name="Ramesh", diagnosis="d", admitting_doctor="Dr")
    return Admission.objects.create(
        patient=patient, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("1000"), status=AdmissionStatus.ACTIVE,
    )


@pytest.fixture
def inquiry(db):
    return Inquiry.objects.create(name="Suja", phone="911", source="OP_CONSULT")


# --- aftercare on discharge -----------------------------------------------

def test_discharge_schedules_aftercare(admin_client, admission):
    result = admin_client.execute(DISCHARGE, {"id": str(admission.id)})
    assert result.get("errors") is None
    fu = FollowUp.objects.get(admission=admission, kind=FollowUpKind.AFTERCARE)
    assert fu.patient_id == admission.patient_id
    assert fu.follow_up_date == date.today() + timedelta(days=30)


def test_reconcile_backfills_and_is_idempotent(db):
    p = Patient.objects.create(name="Old", diagnosis="d", admitting_doctor="Dr")
    Admission.objects.create(
        patient=p, admission_date=date(2026, 1, 1), discharge_date=date(2026, 2, 1),
        status=AdmissionStatus.DISCHARGED, monthly_fee=Decimal("1000"),
    )
    out = StringIO()
    call_command("reconcile_aftercare", stdout=out)
    assert "Scheduled 1" in out.getvalue()
    assert FollowUp.objects.filter(kind=FollowUpKind.AFTERCARE).count() == 1

    # Second run adds nothing.
    call_command("reconcile_aftercare", stdout=StringIO())
    assert FollowUp.objects.filter(kind=FollowUpKind.AFTERCARE).count() == 1


# --- OP nudge on consult --------------------------------------------------

def test_set_consulted_schedules_op_nudge(pro_client, inquiry):
    pro_client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": "2026-08-01"})
    fu = FollowUp.objects.get(inquiry=inquiry, kind=FollowUpKind.OP_NUDGE)
    assert fu.patient_id is None
    assert fu.follow_up_date == date(2026, 8, 4)      # +3 days


def test_op_nudge_idempotent_and_cleared(pro_client, inquiry):
    pro_client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": "2026-08-01"})
    pro_client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": "2026-08-02"})
    assert FollowUp.objects.filter(inquiry=inquiry, kind=FollowUpKind.OP_NUDGE).count() == 1

    # Clearing the consult date drops the pending nudge.
    pro_client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": None})
    assert not FollowUp.objects.filter(
        inquiry=inquiry, kind=FollowUpKind.OP_NUDGE, is_done=False
    ).exists()


def test_create_inquiry_with_consult_schedules_nudge(pro_client):
    pro_client.execute(CREATE, {"data": {
        "name": "Bala", "source": "OP_CONSULT", "consultedOn": "2026-07-15",
    }})
    inq = Inquiry.objects.get(name="Bala")
    assert FollowUp.objects.filter(inquiry=inq, kind=FollowUpKind.OP_NUDGE).exists()


# --- lead follow-ups on the due list --------------------------------------

def test_lead_nudge_appears_on_due_list(pro_client, inquiry):
    FollowUp.objects.create(
        inquiry=inquiry, kind=FollowUpKind.OP_NUDGE, note="nudge",
        follow_up_date=date.today() - timedelta(days=1),
    )
    result = pro_client.execute(DUE, {})
    rows = result["data"]["dueFollowUps"]
    assert any(r["kind"] == "OP_NUDGE" and r["subjectName"] == "Suja" for r in rows)


def test_mark_lead_nudge_done(pro_client, inquiry):
    fu = FollowUp.objects.create(
        inquiry=inquiry, kind=FollowUpKind.OP_NUDGE,
        follow_up_date=date.today() - timedelta(days=1),
    )
    result = pro_client.execute(MARK_DONE, {"id": str(fu.id)})
    assert result.get("errors") is None
    fu.refresh_from_db()
    assert fu.is_done is True
    # Logged on the inquiry timeline.
    assert inquiry.activities.filter(type="FOLLOW_UP").count() == 1
