"""Tests for the createVitalReading mutation and threshold flagging."""
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
    VitalReading,
    VitalsThreshold,
    VitalType,
)

CREATE_VITAL = """
mutation CreateVital(
  $admissionId: ID!
  $session: VitalSessionEnum!
  $bpSystolic: Int!
  $bpDiastolic: Int!
  $pulse: Int!
  $temperature: Decimal!
  $spo2: Int!
  $weight: Decimal
  $notes: String
) {
  createVitalReading(
    admissionId: $admissionId
    session: $session
    bpSystolic: $bpSystolic
    bpDiastolic: $bpDiastolic
    pulse: $pulse
    temperature: $temperature
    spo2: $spo2
    weight: $weight
    notes: $notes
  ) {
    id
    session
    recordedAt
    hasFlag
    flaggedVitals
  }
}
"""

# Default thresholds mirroring the seed command.
THRESHOLDS = {
    VitalType.BP_SYSTOLIC: (90, 180),
    VitalType.BP_DIASTOLIC: (60, 110),
    VitalType.PULSE: (50, 120),
    VitalType.TEMPERATURE: (Decimal("95.0"), Decimal("100.4")),
    VitalType.SPO2: (90, None),
    VitalType.WEIGHT: (None, None),
}


@pytest.fixture
def admission(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    return Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )


@pytest.fixture
def thresholds(db):
    for vital_type, (below, above) in THRESHOLDS.items():
        VitalsThreshold.objects.create(
            vital_type=vital_type, below_threshold=below, above_threshold=above
        )


def _vitals(admission, **overrides):
    """A set of in-range vitals; override individual fields to force breaches."""
    data = {
        "admissionId": str(admission.id),
        "session": "AM",
        "bpSystolic": 120,
        "bpDiastolic": 80,
        "pulse": 72,
        "temperature": "98.6",
        "spo2": 98,
        "weight": "60.5",
        "notes": "",
    }
    data.update(overrides)
    return data


def test_nurse_can_create_reading(nurse_client, admission, thresholds):
    result = nurse_client.execute(CREATE_VITAL, _vitals(admission))
    assert result.get("errors") is None
    reading = result["data"]["createVitalReading"]
    assert reading["session"] == "AM"
    assert reading["recordedAt"] is not None  # server-stamped
    assert reading["hasFlag"] is False
    assert reading["flaggedVitals"] == []
    assert VitalReading.objects.count() == 1


@pytest.mark.parametrize(
    "override, expected_flag",
    [
        ({"bpSystolic": 185}, "BP_SYSTOLIC"),   # > 180
        ({"bpSystolic": 85}, "BP_SYSTOLIC"),    # < 90
        ({"bpDiastolic": 115}, "BP_DIASTOLIC"), # > 110
        ({"pulse": 45}, "PULSE"),               # < 50
        ({"pulse": 130}, "PULSE"),              # > 120
        ({"temperature": "101.0"}, "TEMPERATURE"),  # > 100.4
        ({"temperature": "94.5"}, "TEMPERATURE"),   # < 95.0
        ({"spo2": 85}, "SPO2"),                 # < 90
    ],
)
def test_flag_set_for_each_vital_type(
    nurse_client, admission, thresholds, override, expected_flag
):
    result = nurse_client.execute(CREATE_VITAL, _vitals(admission, **override))
    reading = result["data"]["createVitalReading"]
    assert reading["hasFlag"] is True
    assert expected_flag in reading["flaggedVitals"]

    saved = VitalReading.objects.latest("id")
    assert saved.has_flag is True


def test_weight_never_flags_without_threshold(nurse_client, admission, thresholds):
    # WEIGHT has no bounds configured, so even an extreme value doesn't flag.
    result = nurse_client.execute(CREATE_VITAL, _vitals(admission, weight="200.0"))
    reading = result["data"]["createVitalReading"]
    assert reading["hasFlag"] is False


def test_duplicate_am_pm_same_day_is_allowed(nurse_client, admission, thresholds):
    first = nurse_client.execute(CREATE_VITAL, _vitals(admission, session="AM"))
    second = nurse_client.execute(CREATE_VITAL, _vitals(admission, session="AM"))
    assert first.get("errors") is None
    assert second.get("errors") is None
    # Two AM readings on the same day both persist — not blocked.
    assert VitalReading.objects.filter(admission=admission, session="AM").count() == 2


def test_admin_can_create_reading(admin_client, admission, thresholds):
    result = admin_client.execute(CREATE_VITAL, _vitals(admission))
    assert result.get("errors") is None
    assert result["data"]["createVitalReading"]["id"]


def test_finance_role_rejected(finance_client, admission, thresholds):
    result = finance_client.execute(CREATE_VITAL, _vitals(admission))
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    assert VitalReading.objects.count() == 0


def test_missing_threshold_row_does_not_crash(nurse_client, admission):
    # No VitalsThreshold rows at all — reading saves, nothing flagged.
    result = nurse_client.execute(CREATE_VITAL, _vitals(admission, spo2=10))
    assert result.get("errors") is None
    assert result["data"]["createVitalReading"]["hasFlag"] is False
