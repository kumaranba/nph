"""Tests for the max-inpatient-days limit and the force-discharge reminder list.

The clock runs from admission_date; the list surfaces active admissions within
30 days of (or past) the limit. 0 disables the feature.
"""
from datetime import date, timedelta

import pytest

from api.models import (
    Admission, AdmissionStatus, Patient, SystemSetting,
)

LIST = """
query {
  forceDischargeDueList {
    forceDischargeDate daysRemaining
    admission { id patient { name } }
  }
}
"""

SET = """
mutation($n: Int!) {
  updateSettings(maxInpatientDays: $n) { maxInpatientDays }
}
"""


def _adm(days_ago, name="Ravi", status=AdmissionStatus.ACTIVE):
    p = Patient.objects.create(name=name, diagnosis="d", admitting_doctor="Dr")
    return Admission.objects.create(
        patient=p, admission_date=date.today() - timedelta(days=days_ago),
        monthly_fee=1, status=status,
    )


@pytest.fixture
def limit_180(db):
    s = SystemSetting.load()
    s.max_inpatient_days = 180
    s.save()
    return s


def test_disabled_when_limit_zero(admin_client, db):
    SystemSetting.load()  # default max_inpatient_days = 0
    _adm(500)
    assert admin_client.execute(LIST)["data"]["forceDischargeDueList"] == []


def test_lists_admission_within_a_month_of_limit(admin_client, limit_180):
    # 160 days in → 20 days to the 180-day limit → within the 30-day window.
    _adm(160, name="Due")
    # 100 days in → 80 days left → not yet in the window.
    _adm(100, name="Early")
    rows = admin_client.execute(LIST)["data"]["forceDischargeDueList"]
    names = [r["admission"]["patient"]["name"] for r in rows]
    assert names == ["Due"]
    assert rows[0]["daysRemaining"] == 20


def test_overdue_included_and_sorted_first(admin_client, limit_180):
    _adm(200, name="Overdue")   # 20 days past the limit
    _adm(170, name="Soon")      # 10 days left
    rows = admin_client.execute(LIST)["data"]["forceDischargeDueList"]
    names = [r["admission"]["patient"]["name"] for r in rows]
    assert names == ["Overdue", "Soon"]        # oldest admission (most overdue) first
    assert rows[0]["daysRemaining"] == -20


def test_discharged_admissions_excluded(admin_client, limit_180):
    _adm(200, name="Gone", status=AdmissionStatus.DISCHARGED)
    assert admin_client.execute(LIST)["data"]["forceDischargeDueList"] == []


def test_admin_sets_max_days(admin_client, db):
    r = admin_client.execute(SET, {"n": 365})
    assert r.get("errors") is None
    assert r["data"]["updateSettings"]["maxInpatientDays"] == 365
    assert SystemSetting.load().max_inpatient_days == 365


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "pro_client"])
def test_only_admin_sets_max_days(request, client_name, db):
    client = request.getfixturevalue(client_name)
    assert client.execute(SET, {"n": 100})["errors"]
