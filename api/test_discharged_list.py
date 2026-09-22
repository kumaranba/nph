"""Tests for the dischargedList query — search by tag, sort by discharge date."""
from datetime import date
from decimal import Decimal

import pytest

from api.models import Admission, AdmissionStatus, Patient, Tag

DISCHARGED = """
query($tag: String, $desc: Boolean) {
  dischargedList(tag: $tag, sortDesc: $desc) {
    name dischargeDate dischargeType tags
  }
}
"""


def _discharged(name, discharge_date, *tags, discharge_type="RECOVERED"):
    patient = Patient.objects.create(name=name, diagnosis="d", admitting_doctor="Dr")
    for t in tags:
        tag, _ = Tag.get_or_create_normalized(t)
        patient.tags.add(tag)
    Admission.objects.create(
        patient=patient, admission_date=date(2025, 1, 1),
        monthly_fee=Decimal("5000"), status=AdmissionStatus.DISCHARGED,
        discharge_date=discharge_date, discharge_type=discharge_type,
    )
    return patient


@pytest.fixture
def dataset(db):
    _discharged("Alpha", date(2026, 3, 1), "Aggressive")
    _discharged("Beta", date(2026, 6, 15), "Aggressive", "Diabetes")
    _discharged("Gamma", date(2026, 1, 20))  # no tags
    # An active patient must NOT appear.
    active = Patient.objects.create(name="Active", diagnosis="d", admitting_doctor="Dr")
    Admission.objects.create(
        patient=active, admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("5000"), status=AdmissionStatus.ACTIVE,
    )


def test_lists_discharged_only_newest_first(finance_client, dataset):
    rows = finance_client.execute(DISCHARGED, {"desc": True})["data"]["dischargedList"]
    assert [r["name"] for r in rows] == ["Beta", "Alpha", "Gamma"]
    assert "Active" not in [r["name"] for r in rows]


def test_sort_ascending(finance_client, dataset):
    rows = finance_client.execute(DISCHARGED, {"desc": False})["data"]["dischargedList"]
    assert [r["name"] for r in rows] == ["Gamma", "Alpha", "Beta"]


def test_search_by_tag(finance_client, dataset):
    rows = finance_client.execute(
        DISCHARGED, {"tag": "aggressive"}
    )["data"]["dischargedList"]
    assert {r["name"] for r in rows} == {"Alpha", "Beta"}
    # Tags are carried through, itemised as labels.
    beta = next(r for r in rows if r["name"] == "Beta")
    assert set(beta["tags"]) == {"Aggressive", "Diabetes"}


def test_nurse_cannot_access(nurse_client, dataset):
    result = nurse_client.execute(DISCHARGED, {})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


# --- re-admission exclusion, name/date filters, monthly summary -------------

DISCHARGED_FILTERED = """
query($search: String, $from: Date, $to: Date) {
  dischargedList(search: $search, dischargedFrom: $from, dischargedTo: $to) {
    name dischargeDate
  }
}
"""

MONTHLY = """
query { dischargedMonthlySummary { month count } }
"""


def _readmit(patient):
    """Give a discharged patient a current ACTIVE admission (a re-admission)."""
    Admission.objects.create(
        patient=patient, admission_date=date(2026, 7, 1),
        monthly_fee=Decimal("5000"), status=AdmissionStatus.ACTIVE,
    )


def test_readmitted_patient_hidden_from_discharged_list(finance_client, dataset):
    beta = Patient.objects.get(name="Beta")
    _readmit(beta)
    rows = finance_client.execute(DISCHARGED, {"desc": True})["data"]["dischargedList"]
    names = [r["name"] for r in rows]
    assert "Beta" not in names          # re-admitted → not in discharged list
    assert set(names) == {"Alpha", "Gamma"}


def test_filter_by_patient_name(finance_client, dataset):
    rows = finance_client.execute(
        DISCHARGED_FILTERED, {"search": "alph"}
    )["data"]["dischargedList"]
    assert {r["name"] for r in rows} == {"Alpha"}


def test_filter_by_discharge_date_range(finance_client, dataset):
    # Alpha 2026-03-01, Beta 2026-06-15, Gamma 2026-01-20.
    rows = finance_client.execute(
        DISCHARGED_FILTERED, {"from": "2026-02-01", "to": "2026-05-01"}
    )["data"]["dischargedList"]
    assert {r["name"] for r in rows} == {"Alpha"}


def test_monthly_summary_counts_and_excludes_readmitted(finance_client, dataset):
    summary = finance_client.execute(MONTHLY)["data"]["dischargedMonthlySummary"]
    # Newest month first: 2026-06 (Beta), 2026-03 (Alpha), 2026-01 (Gamma).
    assert summary == [
        {"month": "2026-06", "count": 1},
        {"month": "2026-03", "count": 1},
        {"month": "2026-01", "count": 1},
    ]
    # Re-admitting Beta drops the 2026-06 bucket.
    _readmit(Patient.objects.get(name="Beta"))
    after = finance_client.execute(MONTHLY)["data"]["dischargedMonthlySummary"]
    assert {row["month"] for row in after} == {"2026-03", "2026-01"}
