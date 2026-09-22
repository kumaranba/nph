"""Planned discharge date — ADMIN sets/edits/clears a target discharge date on
active admissions to forecast bed vacancies; the vacancy list, overdue
highlight, and auto-clear on discharge."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Patient,
    Room,
)

SET = """
mutation($id: ID!, $d: Date!) {
  setPlannedDischargeDate(admissionId: $id, plannedDischargeDate: $d) {
    id plannedDischargeDate isDischargeOverdue daysUntilPlannedDischarge
  }
}
"""
CLEAR = """
mutation($id: ID!) {
  clearPlannedDischargeDate(admissionId: $id) { id plannedDischargeDate }
}
"""
LIST = """
query($search: String, $from: Date, $to: Date, $overdue: Boolean) {
  plannedDischargeList(search: $search, plannedFrom: $from, plannedTo: $to, overdueOnly: $overdue) {
    plannedDischargeDate daysRemaining isOverdue
    admission { id patient { name } }
  }
}
"""
OVERDUE_COUNT = "query { plannedDischargeOverdueCount }"
DISCHARGE = """
mutation($id: ID!) {
  dischargePatient(admissionId: $id) { admission { status plannedDischargeDate } }
}
"""


def _admission(name="Ravi", status=AdmissionStatus.ACTIVE, planned=None):
    patient = Patient.objects.create(name=name, diagnosis="d", admitting_doctor="Dr")
    room = Room.objects.create(name=f"Ward-{name}", capacity=2)
    bed = Bed.objects.create(room=room, label="B1", status=BedStatus.OCCUPIED)
    return Admission.objects.create(
        patient=patient, bed=bed, admission_date=date.today() - timedelta(days=10),
        monthly_fee=Decimal("5000"), status=status, planned_discharge_date=planned,
    )


@pytest.fixture
def admission(db):
    return _admission()


# --- set / edit / clear (RBAC) ----------------------------------------------

def test_admin_sets_planned_discharge_date(admin_client, admission):
    d = (date.today() + timedelta(days=5)).isoformat()
    res = admin_client.execute(SET, {"id": str(admission.id), "d": d})
    assert res.get("errors") is None
    out = res["data"]["setPlannedDischargeDate"]
    assert out["plannedDischargeDate"] == d
    assert out["isDischargeOverdue"] is False
    assert out["daysUntilPlannedDischarge"] == 5
    admission.refresh_from_db()
    assert admission.planned_discharge_date.isoformat() == d


def test_edit_overwrites_previous_plan(admin_client, admission):
    admin_client.execute(SET, {"id": str(admission.id),
                               "d": (date.today() + timedelta(days=3)).isoformat()})
    new_d = (date.today() + timedelta(days=9)).isoformat()
    admin_client.execute(SET, {"id": str(admission.id), "d": new_d})
    admission.refresh_from_db()
    assert admission.planned_discharge_date.isoformat() == new_d


def test_clear_planned_discharge_date(admin_client):
    adm = _admission(planned=date.today() + timedelta(days=4))
    res = admin_client.execute(CLEAR, {"id": str(adm.id)})
    assert res.get("errors") is None
    assert res["data"]["clearPlannedDischargeDate"]["plannedDischargeDate"] is None
    adm.refresh_from_db()
    assert adm.planned_discharge_date is None


def test_set_forbidden_for_non_admin(finance_client, pro_client, nurse_client, admission):
    d = (date.today() + timedelta(days=5)).isoformat()
    for client in (finance_client, pro_client, nurse_client):
        res = client.execute(SET, {"id": str(admission.id), "d": d})
        assert res.get("errors"), "expected permission error"
    admission.refresh_from_db()
    assert admission.planned_discharge_date is None


# --- validation -------------------------------------------------------------

def test_rejects_past_date(admin_client, admission):
    res = admin_client.execute(
        SET, {"id": str(admission.id), "d": (date.today() - timedelta(days=1)).isoformat()}
    )
    assert res.get("errors") and "past" in res["errors"][0]["message"].lower()


def test_rejects_when_discharged(admin_client):
    adm = _admission(status=AdmissionStatus.DISCHARGED)
    res = admin_client.execute(
        SET, {"id": str(adm.id), "d": (date.today() + timedelta(days=2)).isoformat()}
    )
    assert res.get("errors") and "active" in res["errors"][0]["message"].lower()


# --- overdue highlight ------------------------------------------------------

def test_overdue_flag_and_count(admin_client):
    _admission(name="LateOne", planned=date.today() - timedelta(days=2))
    _admission(name="OnTrack", planned=date.today() + timedelta(days=3))
    count = admin_client.execute(OVERDUE_COUNT)["data"]["plannedDischargeOverdueCount"]
    assert count == 1


# --- vacancy list -----------------------------------------------------------

def test_list_sorted_and_filtered(admin_client):
    _admission(name="Soon", planned=date.today() + timedelta(days=2))
    _admission(name="Later", planned=date.today() + timedelta(days=20))
    _admission(name="Overdue", planned=date.today() - timedelta(days=1))
    _admission(name="NoPlan")  # excluded — no planned date

    rows = admin_client.execute(LIST, {})["data"]["plannedDischargeList"]
    names = [r["admission"]["patient"]["name"] for r in rows]
    assert names == ["Overdue", "Soon", "Later"]  # soonest first
    assert "NoPlan" not in names

    overdue = admin_client.execute(LIST, {"overdue": True})["data"]["plannedDischargeList"]
    assert [r["admission"]["patient"]["name"] for r in overdue] == ["Overdue"]

    searched = admin_client.execute(LIST, {"search": "soon"})["data"]["plannedDischargeList"]
    assert [r["admission"]["patient"]["name"] for r in searched] == ["Soon"]


def test_list_date_range(admin_client):
    _admission(name="Jan", planned=date.today() + timedelta(days=2))
    _admission(name="Feb", planned=date.today() + timedelta(days=40))
    rows = admin_client.execute(
        LIST,
        {"from": date.today().isoformat(),
         "to": (date.today() + timedelta(days=10)).isoformat()},
    )["data"]["plannedDischargeList"]
    assert [r["admission"]["patient"]["name"] for r in rows] == ["Jan"]


def test_list_forbidden_for_nurse(nurse_client, admission):
    res = nurse_client.execute(LIST, {})
    assert res["data"] is None
    assert "Permission denied" in res["errors"][0]["message"]


# --- auto-clear on discharge ------------------------------------------------

def test_discharge_nulls_planned_date(admin_client):
    adm = _admission(planned=date.today() + timedelta(days=3))
    res = admin_client.execute(DISCHARGE, {"id": str(adm.id)})
    assert res.get("errors") is None
    result = res["data"]["dischargePatient"]["admission"]
    assert result["status"] == "DISCHARGED"
    assert result["plannedDischargeDate"] is None
    adm.refresh_from_db()
    assert adm.planned_discharge_date is None
