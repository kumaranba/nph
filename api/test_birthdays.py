"""Tests for the upcoming-birthdays reminder (in-patients, 7-day window)."""
from datetime import date, timedelta

import pytest

from api.models import Admission, AdmissionStatus, Patient

QUERY = """
query($within: Int) {
  upcomingBirthdays(withinDays: $within) {
    turningAge daysUntil bedLabel birthday
    patient { name }
  }
}
"""


def _inpatient(name, dob, *, active=True, bed=None):
    p = Patient.objects.create(
        name=name, date_of_birth=dob, diagnosis="d", admitting_doctor="Dr",
    )
    Admission.objects.create(
        patient=p, bed=bed, admission_date=date(2026, 1, 1), monthly_fee=1,
        status=AdmissionStatus.ACTIVE if active else AdmissionStatus.DISCHARGED,
    )
    return p


def _dob_offset(days, years_ago):
    """A date of birth whose birthday lands `days` from today, born `years_ago`."""
    target = date.today() + timedelta(days=days)
    return target.replace(year=target.year - years_ago)


def test_lists_birthday_today_and_within_window(admin_client, db):
    _inpatient("Today", _dob_offset(0, 40))
    _inpatient("In5", _dob_offset(5, 30))
    _inpatient("In10", _dob_offset(10, 25))     # outside 7-day window
    rows = admin_client.execute(QUERY, {"within": 7})["data"]["upcomingBirthdays"]
    names = [r["patient"]["name"] for r in rows]
    assert names == ["Today", "In5"]            # soonest first, In10 excluded
    assert rows[0]["daysUntil"] == 0
    assert rows[0]["turningAge"] == 40


def test_excludes_discharged_and_no_dob(admin_client, db):
    _inpatient("Gone", _dob_offset(1, 50), active=False)
    Patient.objects.create(name="NoDob", diagnosis="d", admitting_doctor="Dr")
    rows = admin_client.execute(QUERY, {"within": 7})["data"]["upcomingBirthdays"]
    assert rows == []


def test_default_window_is_seven_days(admin_client, db):
    _inpatient("In7", _dob_offset(7, 20))
    _inpatient("In8", _dob_offset(8, 20))
    rows = admin_client.execute(
        "{ upcomingBirthdays { patient { name } } }"
    )["data"]["upcomingBirthdays"]
    names = [r["patient"]["name"] for r in rows]
    assert names == ["In7"]


def test_bed_label_included(admin_client, db):
    from api.models import Bed, BedStatus, Room
    room = Room.objects.create(name="MW1", capacity=1)
    bed = Bed.objects.create(room=room, label="B3", status=BedStatus.OCCUPIED)
    _inpatient("Ravi", _dob_offset(2, 33), bed=bed)
    rows = admin_client.execute(QUERY, {"within": 7})["data"]["upcomingBirthdays"]
    assert rows[0]["bedLabel"] == "B3"
