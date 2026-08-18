"""Tests for the feesDueList query."""
from datetime import date
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

# Pinned "today" so cycle-date math is deterministic regardless of run date.
TODAY = date(2026, 6, 15)

FEES_DUE = """
query FeesDue($withinDays: Int) {
  feesDueList(withinDays: $withinDays) {
    name
    patientId
    room
    dueDate
    amountDue
    daysUntilDue
  }
}
"""


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr("api.schema._today", lambda: TODAY)


@pytest.fixture
def room(db):
    return Room.objects.create(name="Ward A", capacity=10)


def _admit(room, *, name, anchor_day, label, fee="20000.00"):
    """Create an active admission anchored on `anchor_day` in May 2026 (before
    today), so its next cycle date is that day-of-month in June."""
    bed = Bed.objects.create(room=room, label=label, status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name=name, diagnosis="dx", admitting_doctor="Dr. X"
    )
    return Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 5, anchor_day),
        monthly_fee=Decimal(fee),
        status=AdmissionStatus.ACTIVE,
    )


def test_returns_only_patients_due_within_window(admin_client, room):
    _admit(room, name="Due Today", anchor_day=15, label="B1")    # days 0
    _admit(room, name="Due In 3", anchor_day=18, label="B2")     # days 3
    _admit(room, name="Due In 5", anchor_day=20, label="B3")     # days 5
    _admit(room, name="Due In 25", anchor_day=10, label="B4")    # days 25 (Jul 10)

    result = admin_client.execute(FEES_DUE, {"withinDays": 5})
    assert result.get("errors") is None
    rows = result["data"]["feesDueList"]

    # Within 5 days: today(0), 3, 5 — sorted by due date. The 25-day one excluded.
    assert [r["name"] for r in rows] == ["Due Today", "Due In 3", "Due In 5"]
    assert [r["daysUntilDue"] for r in rows] == [0, 3, 5]
    assert rows[0]["dueDate"] == "2026-06-15"
    assert rows[0]["room"] == "Ward A"
    assert Decimal(str(rows[0]["amountDue"])) == Decimal("20000.00")


def test_boundary_day_is_included(admin_client, room):
    _admit(room, name="On Boundary", anchor_day=20, label="C1")  # days 5

    # withinDays == daysUntilDue → included.
    included = admin_client.execute(FEES_DUE, {"withinDays": 5})
    assert [r["name"] for r in included["data"]["feesDueList"]] == ["On Boundary"]

    # One day tighter → excluded.
    excluded = admin_client.execute(FEES_DUE, {"withinDays": 4})
    assert excluded["data"]["feesDueList"] == []


def test_within_days_defaults_to_system_setting(admin_client, room):
    from api.models import SystemSetting

    setting = SystemSetting.load()
    setting.fee_due_warning_days = 3
    setting.save()

    _admit(room, name="Due In 3", anchor_day=18, label="D1")  # days 3 (<= 3)
    _admit(room, name="Due In 5", anchor_day=20, label="D2")  # days 5 (> 3)

    # No withinDays passed → falls back to the SystemSetting value (3).
    result = admin_client.execute(FEES_DUE, {"withinDays": None})
    assert result.get("errors") is None
    assert [r["name"] for r in result["data"]["feesDueList"]] == ["Due In 3"]


def test_finance_role_allowed(finance_client, room):
    _admit(room, name="Due In 3", anchor_day=18, label="E1")
    result = finance_client.execute(FEES_DUE, {"withinDays": 7})
    assert result.get("errors") is None
    assert [r["name"] for r in result["data"]["feesDueList"]] == ["Due In 3"]


def test_nurse_role_rejected(nurse_client, room):
    _admit(room, name="Due In 3", anchor_day=18, label="F1")
    result = nurse_client.execute(FEES_DUE, {"withinDays": 7})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_discharged_patients_excluded(admin_client, room):
    admission = _admit(room, name="Gone", anchor_day=18, label="G1")
    admission.status = AdmissionStatus.DISCHARGED
    admission.save(update_fields=["status"])

    result = admin_client.execute(FEES_DUE, {"withinDays": 30})
    assert result["data"]["feesDueList"] == []
