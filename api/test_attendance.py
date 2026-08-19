"""Tests for daily staff attendance — mark / bulk-mark / roster / summary + RBAC.

RBAC contract: ADMIN only (Finance, Nurse, PRO have no access). At most one
attendance row per (staff, date); marking again updates it.
"""
from datetime import date, timedelta

import pytest

from api.models import Attendance, AttendanceStatus, Staff


MARK = """
mutation($id: ID!, $date: Date!, $status: AttendanceStatusEnum!) {
  markAttendance(staffId: $id, date: $date, status: $status) {
    id status date staff { id } recordedBy { email }
  }
}
"""

BULK = """
mutation($date: Date!, $entries: [AttendanceEntryInput!]!) {
  bulkMarkAttendance(date: $date, entries: $entries) {
    staff { id name } status
  }
}
"""

ROSTER = """
query($date: Date!) {
  attendanceRoster(date: $date) {
    staff { id name staffCode } status
  }
}
"""

SUMMARY = """
query($id: ID!, $from: Date, $to: Date) {
  attendanceSummary(staffId: $id, dateFrom: $from, dateTo: $to) {
    staff { id } present absent leave halfDay markedDays
  }
}
"""

TODAY = str(date.today())


@pytest.fixture
def staff(db):
    return Staff.objects.create(name="Lakshmi", designation="COOK")


# --- mark -----------------------------------------------------------------

def test_admin_marks_attendance(admin_client, staff):
    result = admin_client.execute(
        MARK, {"id": str(staff.id), "date": TODAY, "status": "PRESENT"}
    )
    assert result.get("errors") is None
    data = result["data"]["markAttendance"]
    assert data["status"] == "PRESENT"
    assert data["staff"]["id"] == str(staff.id)
    assert data["recordedBy"]["email"] == "admin@nph.test"
    assert Attendance.objects.count() == 1


def test_mark_is_upsert(admin_client, staff):
    admin_client.execute(MARK, {"id": str(staff.id), "date": TODAY, "status": "PRESENT"})
    admin_client.execute(MARK, {"id": str(staff.id), "date": TODAY, "status": "ABSENT"})
    assert Attendance.objects.count() == 1       # updated, not duplicated
    assert Attendance.objects.get().status == AttendanceStatus.ABSENT


def test_cannot_mark_future_date(admin_client, staff):
    future = str(date.today() + timedelta(days=1))
    result = admin_client.execute(
        MARK, {"id": str(staff.id), "date": future, "status": "PRESENT"}
    )
    assert result["errors"]
    assert Attendance.objects.count() == 0


def test_mark_unknown_staff(admin_client):
    result = admin_client.execute(
        MARK, {"id": "999999", "date": TODAY, "status": "PRESENT"}
    )
    assert result["errors"]


# --- bulk mark ------------------------------------------------------------

def test_bulk_mark_roster(admin_client, staff):
    other = Staff.objects.create(name="Ravi", designation="SECURITY")
    result = admin_client.execute(BULK, {
        "date": TODAY,
        "entries": [
            {"staffId": str(staff.id), "status": "PRESENT"},
            {"staffId": str(other.id), "status": "LEAVE"},
        ],
    })
    assert result.get("errors") is None
    by_status = {r["staff"]["name"]: r["status"] for r in result["data"]["bulkMarkAttendance"]}
    assert by_status == {"Lakshmi": "PRESENT", "Ravi": "LEAVE"}
    assert Attendance.objects.count() == 2


def test_bulk_mark_updates_existing(admin_client, staff):
    Attendance.objects.create(staff=staff, date=date.today(), status="PRESENT")
    admin_client.execute(BULK, {
        "date": TODAY,
        "entries": [{"staffId": str(staff.id), "status": "HALF_DAY"}],
    })
    assert Attendance.objects.count() == 1
    assert Attendance.objects.get().status == AttendanceStatus.HALF_DAY


def test_bulk_mark_rejects_unknown_staff(admin_client, staff):
    result = admin_client.execute(BULK, {
        "date": TODAY,
        "entries": [
            {"staffId": str(staff.id), "status": "PRESENT"},
            {"staffId": "999999", "status": "ABSENT"},
        ],
    })
    assert result["errors"]
    assert Attendance.objects.count() == 0       # atomic — nothing written


def test_bulk_mark_future_date_rejected(admin_client, staff):
    future = str(date.today() + timedelta(days=1))
    result = admin_client.execute(BULK, {
        "date": future,
        "entries": [{"staffId": str(staff.id), "status": "PRESENT"}],
    })
    assert result["errors"]
    assert Attendance.objects.count() == 0


# --- roster ---------------------------------------------------------------

def test_roster_pairs_active_staff_with_status(admin_client, staff):
    other = Staff.objects.create(name="Ravi", designation="SECURITY")
    Staff.objects.create(name="Retired", is_active=False)   # excluded
    Attendance.objects.create(staff=staff, date=date.today(), status="PRESENT")

    result = admin_client.execute(ROSTER, {"date": TODAY})
    rows = {r["staff"]["name"]: r["status"] for r in result["data"]["attendanceRoster"]}
    assert rows == {"Lakshmi": "PRESENT", "Ravi": None}      # only active; Ravi unmarked


def test_roster_status_is_per_date(admin_client, staff):
    Attendance.objects.create(staff=staff, date=date(2026, 1, 1), status="ABSENT")
    result = admin_client.execute(ROSTER, {"date": TODAY})
    rows = {r["staff"]["name"]: r["status"] for r in result["data"]["attendanceRoster"]}
    assert rows == {"Lakshmi": None}       # today unmarked, Jan 1 doesn't leak


# --- summary --------------------------------------------------------------

def test_summary_counts_by_status(admin_client, staff):
    for d, s in [
        (date(2026, 3, 1), "PRESENT"),
        (date(2026, 3, 2), "PRESENT"),
        (date(2026, 3, 3), "ABSENT"),
        (date(2026, 3, 4), "LEAVE"),
        (date(2026, 3, 5), "HALF_DAY"),
    ]:
        Attendance.objects.create(staff=staff, date=d, status=s)

    result = admin_client.execute(SUMMARY, {"id": str(staff.id)})
    s = result["data"]["attendanceSummary"]
    assert (s["present"], s["absent"], s["leave"], s["halfDay"]) == (2, 1, 1, 1)
    assert s["markedDays"] == 5


def test_summary_respects_date_range(admin_client, staff):
    Attendance.objects.create(staff=staff, date=date(2026, 3, 1), status="PRESENT")
    Attendance.objects.create(staff=staff, date=date(2026, 4, 1), status="ABSENT")
    result = admin_client.execute(
        SUMMARY, {"id": str(staff.id), "from": "2026-03-01", "to": "2026-03-31"}
    )
    s = result["data"]["attendanceSummary"]
    assert s["present"] == 1 and s["absent"] == 0 and s["markedDays"] == 1


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize(
    "client_name", ["finance_client", "nurse_client", "pro_client", "anonymous_client"]
)
def test_roster_forbidden_for_non_admin(request, client_name, staff):
    client = request.getfixturevalue(client_name)
    result = client.execute(ROSTER, {"date": TODAY})
    assert result["errors"]
    assert result["data"] is None or result["data"]["attendanceRoster"] is None


@pytest.mark.parametrize(
    "client_name", ["finance_client", "nurse_client", "pro_client"]
)
def test_mark_forbidden_for_non_admin(request, client_name, staff):
    client = request.getfixturevalue(client_name)
    result = client.execute(
        MARK, {"id": str(staff.id), "date": TODAY, "status": "PRESENT"}
    )
    assert result["errors"]
    assert Attendance.objects.count() == 0
