"""Tests for the canteen meal count — daily counts, veg/non-veg split, costs.

Service tested directly with a deterministic ``today``; GraphQL + RBAC through
the API. Sep 2026: the 2nd is a Wednesday, the 6th is a Sunday (split days).
"""
from datetime import date
from decimal import Decimal

import pytest

from api.canteen import build_canteen_report
from api.models import (
    Admission, Attendance, FoodRate, Patient, Staff, StaffMealRate,
)


def _patient(name, gender="", pref=""):
    return Patient.objects.create(
        name=name, diagnosis="d", admitting_doctor="Dr",
        gender=gender, food_preference=pref,
    )


def _admit(name, adm, dis=None, gender="", pref=""):
    return Admission.objects.create(
        patient=_patient(name, gender, pref),
        admission_date=adm, discharge_date=dis, monthly_fee=Decimal("1000"),
        status="DISCHARGED" if dis else "ACTIVE",
    )


def _staff(name, gender="MALE"):
    return Staff.objects.create(name=name, gender=gender)


@pytest.fixture
def rates(db):
    FoodRate.objects.create(amount=Decimal("120"), effective_from=date(2026, 1, 1))
    StaffMealRate.objects.create(amount=Decimal("1500"), effective_from=date(2026, 1, 1))


SEP_END = date(2026, 9, 30)


# --- daily counts ---------------------------------------------------------

def test_patient_counts_by_gender(rates):
    _admit("Mp", date(2026, 9, 1), gender="MALE")
    _admit("Fp", date(2026, 9, 1), gender="FEMALE")
    r = build_canteen_report(month="2026-09", today=SEP_END)
    day1 = r.days[0]
    assert day1.male_patients == 1 and day1.female_patients == 1
    assert day1.patients == 2


def test_staff_from_attendance_present_only(rates):
    s1 = _staff("A", "MALE")
    s2 = _staff("B", "FEMALE")
    Attendance.objects.create(staff=s1, date=date(2026, 9, 1), status="PRESENT")
    Attendance.objects.create(staff=s2, date=date(2026, 9, 1), status="HALF_DAY")
    Attendance.objects.create(staff=s1, date=date(2026, 9, 2), status="ABSENT")
    r = build_canteen_report(month="2026-09", today=SEP_END)
    d1, d2 = r.days[0], r.days[1]
    assert d1.male_staff == 1 and d1.female_staff == 1   # present + half-day
    assert d2.staff == 0                                 # absent doesn't count


def test_veg_nonveg_split_only_on_wed_and_sun(rates):
    # Non-veg male patient, admitted all month.
    _admit("NV", date(2026, 9, 1), gender="MALE", pref="NON_VEG")
    r = build_canteen_report(month="2026-09", today=SEP_END)
    by_day = {d.day.day: d for d in r.days}
    # 1st = Tuesday → veg only, non-veg portion 0
    assert by_day[1].is_split is False
    assert by_day[1].male_patients_nonveg == 0
    # 2nd = Wednesday → split, the non-veg patient shows in non-veg
    assert by_day[2].is_split is True
    assert by_day[2].male_patients_nonveg == 1
    # 6th = Sunday → split too
    assert by_day[6].is_split is True
    assert by_day[6].male_patients_nonveg == 1


def test_blank_preference_counts_as_veg(rates):
    _admit("Blank", date(2026, 9, 2), gender="FEMALE", pref="")  # Wed
    r = build_canteen_report(month="2026-09", today=SEP_END)
    wed = next(d for d in r.days if d.day.day == 2)
    assert wed.female_patients == 1 and wed.female_patients_nonveg == 0


def test_blank_gender_goes_to_other(rates):
    _admit("NoGender", date(2026, 9, 1), gender="")
    r = build_canteen_report(month="2026-09", today=SEP_END)
    assert r.days[0].other_patients == 1
    assert r.has_other is True


def test_caps_at_today(rates):
    _admit("A", date(2026, 9, 1))
    r = build_canteen_report(month="2026-09", today=date(2026, 9, 3))
    assert len(r.days) == 3        # only 1st–3rd


# --- costs ----------------------------------------------------------------

def test_patient_cost_is_patient_days_times_daily_rate(rates):
    _admit("A", date(2026, 9, 1), dis=date(2026, 9, 3))   # present 1,2,3 = 3 days
    r = build_canteen_report(month="2026-09", today=SEP_END)
    assert r.totals.patient_days == 3
    assert r.patient_cost == Decimal("360")               # 3 × 120


def test_staff_cost_is_flat_per_active_staff(rates):
    _staff("A")
    _staff("B")
    inactive = _staff("C")
    inactive.is_active = False
    inactive.save()
    # No attendance at all → staff still cost the flat monthly rate.
    r = build_canteen_report(month="2026-09", today=SEP_END)
    assert r.active_staff == 2
    assert r.staff_cost == Decimal("3000")                # 2 active × 1500


def test_grand_total_is_patient_plus_staff(rates):
    _admit("A", date(2026, 9, 1), dis=date(2026, 9, 1))   # 1 patient-day
    _staff("S")
    r = build_canteen_report(month="2026-09", today=SEP_END)
    assert r.grand_total_cost == r.patient_cost + r.staff_cost
    assert r.grand_total_cost == Decimal("120") + Decimal("1500")


# --- GraphQL + RBAC -------------------------------------------------------

QUERY = """
query($month: String) {
  canteenReport(month: $month) {
    month dailyRate staffMonthlyRate activeStaff hasOther
    patientCost staffCost grandTotalCost
    totals { patientDays staffDays total }
    days { day dow isSplit malePatients malePatientsNonveg total }
  }
}
"""


def test_canteen_query_works(admin_client, rates):
    # A fully-past month (real "today" is well after July 2026) so the report
    # isn't truncated by the future-day cap.
    _admit("A", date(2026, 7, 1))
    result = admin_client.execute(QUERY, {"month": "2026-07"})
    assert result.get("errors") is None
    assert result["data"]["canteenReport"]["month"] == "2026-07"
    assert len(result["data"]["canteenReport"]["days"]) == 31


@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client", "anonymous_client"])
def test_canteen_forbidden(request, client_name, rates):
    client = request.getfixturevalue(client_name)
    result = client.execute(QUERY, {"month": "2026-09"})
    assert result["errors"]
    assert result["data"] is None or result["data"]["canteenReport"] is None
