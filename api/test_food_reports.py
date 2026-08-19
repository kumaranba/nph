"""Tests for the two food reports — daily vendor list + patient-wise monthly.

Both count a patient-day for every calendar day from admission through
discharge (both inclusive), priced at the effective FoodRate. RBAC:
ADMIN + FINANCE. The service is tested directly (deterministic ``today``); the
GraphQL layer + RBAC are checked through the API.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.food_report import build_food_vendor_list, build_patient_food_report
from api.models import Admission, FoodRate, Patient


def _patient(name):
    return Patient.objects.create(name=name, diagnosis="d", admitting_doctor="Dr")


def _admit(name, adm, dis=None):
    return Admission.objects.create(
        patient=_patient(name), admission_date=adm, discharge_date=dis,
        monthly_fee=Decimal("1000"),
        status="DISCHARGED" if dis else "ACTIVE",
    )


@pytest.fixture
def rate_100(db):
    return FoodRate.objects.create(amount=Decimal("100"), effective_from=date(2026, 1, 1))


# --- daily vendor list ----------------------------------------------------

def test_vendor_list_counts_present_patients(rate_100):
    _admit("A", date(2026, 3, 1))                    # active whole range
    _admit("B", date(2026, 3, 2), date(2026, 3, 3))  # present 2nd–3rd inclusive

    data = build_food_vendor_list(
        date(2026, 3, 1), date(2026, 3, 3), today=date(2026, 3, 31)
    )
    counts = {r.day.day: r.patients for r in data.rows}
    assert counts == {1: 1, 2: 2, 3: 2}              # discharge day (3rd) counted
    # 1 + 2 + 2 = 5 patient-days × 100
    assert data.total_patient_days == 5
    assert data.total_amount == Decimal("500")


def test_vendor_list_clamps_to_today(rate_100):
    _admit("A", date(2026, 3, 1))
    data = build_food_vendor_list(
        date(2026, 3, 1), date(2026, 3, 31), today=date(2026, 3, 2)
    )
    # Only the 1st and 2nd are counted (today = 2nd); no future days.
    assert [r.day.day for r in data.rows] == [1, 2]
    assert data.total_patient_days == 2


def test_vendor_list_uses_per_day_rate(db):
    FoodRate.objects.create(amount=Decimal("100"), effective_from=date(2026, 1, 1))
    FoodRate.objects.create(amount=Decimal("150"), effective_from=date(2026, 3, 3))
    _admit("A", date(2026, 3, 1))
    data = build_food_vendor_list(
        date(2026, 3, 1), date(2026, 3, 4), today=date(2026, 3, 31)
    )
    amounts = {r.day.day: r.amount for r in data.rows}
    assert amounts == {
        1: Decimal("100"), 2: Decimal("100"),
        3: Decimal("150"), 4: Decimal("150"),
    }


# --- patient-wise monthly report ------------------------------------------

def test_report_groups_and_days(rate_100):
    # March 2026, evaluated at month end.
    _admit("Discharged", date(2026, 2, 20), date(2026, 3, 5))    # G1: 1–5 = 5 days
    _admit("NewAdmit", date(2026, 3, 10))                        # G2: 10–31 = 22 days
    _admit("WholeMonth", date(2026, 1, 1))                       # G3: 1–31 = 31 days
    _admit("BothSameMonth", date(2026, 3, 2), date(2026, 3, 4))  # G1 edge: 2–4 = 3 days
    _admit("PriorGone", date(2025, 12, 1), date(2026, 2, 15))    # excluded

    r = build_patient_food_report(month="2026-03", today=date(2026, 3, 31))
    g = {grp.key: grp for grp in r.groups}

    disc = {row.name: row.days for row in g["DISCHARGED"].rows}
    assert disc == {"Discharged": 5, "BothSameMonth": 3}         # edge → G1
    assert g["DISCHARGED"].total_days == 8

    adm = {row.name: row.days for row in g["ADMITTED"].rows}
    assert adm == {"NewAdmit": 22}

    whole = {row.name: row.days for row in g["WHOLE_MONTH"].rows}
    assert whole == {"WholeMonth": 31}

    # No excluded patient anywhere.
    all_names = {row.name for grp in r.groups for row in grp.rows}
    assert "PriorGone" not in all_names


def test_report_amounts_and_totals(rate_100):
    _admit("WholeMonth", date(2026, 1, 1))          # 31 days × 100
    r = build_patient_food_report(month="2026-03", today=date(2026, 3, 31))
    whole = next(g for g in r.groups if g.key == "WHOLE_MONTH")
    assert whole.rows[0].amount == Decimal("3100")
    assert whole.total_amount == Decimal("3100")
    assert r.grand_total_days == 31
    assert r.grand_total_amount == Decimal("3100")


def test_report_ongoing_month_caps_at_today(rate_100):
    _admit("WholeMonth", date(2026, 1, 1))
    # Mid-month: today = 10 March → whole-month patient has 10 days so far.
    r = build_patient_food_report(month="2026-03", today=date(2026, 3, 10))
    whole = next(g for g in r.groups if g.key == "WHOLE_MONTH")
    assert whole.rows[0].days == 10


def test_report_defaults_to_current_month(rate_100):
    today = date.today()
    _admit("Now", date(today.year, today.month, 1))
    r = build_patient_food_report(today=today)
    assert r.month == today.strftime("%Y-%m")


# --- GraphQL + RBAC -------------------------------------------------------

VENDOR = """
query($from: Date!, $to: Date!) {
  foodVendorList(dateFrom: $from, dateTo: $to) {
    totalPatientDays totalAmount rows { day patients amount }
  }
}
"""

REPORT = """
query($month: String) {
  patientFoodReport(month: $month) {
    month rate grandTotalDays grandTotalAmount
    groups { key label totalDays totalAmount rows { name days amount } }
  }
}
"""


def test_vendor_query_works(admin_client, rate_100):
    _admit("A", date(2026, 3, 1))
    result = admin_client.execute(VENDOR, {"from": "2026-03-01", "to": "2026-03-01"})
    assert result.get("errors") is None
    assert result["data"]["foodVendorList"]["totalPatientDays"] == 1


def test_report_query_works(admin_client, rate_100):
    _admit("A", date(2026, 1, 1))
    result = admin_client.execute(REPORT, {"month": "2026-03"})
    assert result.get("errors") is None
    assert len(result["data"]["patientFoodReport"]["groups"]) == 3


def test_vendor_bad_range_rejected(finance_client, rate_100):
    result = finance_client.execute(VENDOR, {"from": "2026-03-05", "to": "2026-03-01"})
    assert result["errors"]


@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client", "anonymous_client"])
def test_food_reports_forbidden(request, client_name, rate_100):
    client = request.getfixturevalue(client_name)
    v = client.execute(VENDOR, {"from": "2026-03-01", "to": "2026-03-02"})
    assert v["errors"]
    r = client.execute(REPORT, {"month": "2026-03"})
    assert r["errors"]
