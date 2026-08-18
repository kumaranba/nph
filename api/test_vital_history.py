"""Tests for the vitalHistory query."""
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Patient,
    Room,
    User,
    UserRole,
    VitalReading,
    VitalSession,
)

VITAL_HISTORY = """
query VitalHistory(
  $patientId: ID!
  $dateFrom: Date
  $dateTo: Date
  $types: [String!]
) {
  vitalHistory(
    patientId: $patientId
    dateFrom: $dateFrom
    dateTo: $dateTo
    types: $types
  ) {
    id
    recordedAt
    pulse
    weight
  }
}
"""


@pytest.fixture
def patient_with_readings(db):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    admission = Admission.objects.create(
        patient=patient,
        bed=bed,
        admission_date=date(2026, 1, 1),
        monthly_fee=Decimal("25000.00"),
        status=AdmissionStatus.ACTIVE,
    )
    nurse = User.objects.create_user(
        email="rn@vitals.test", password="x", role=UserRole.NURSE
    )

    def _reading(day, pulse, weight=None):
        return VitalReading.objects.create(
            admission=admission,
            session=VitalSession.AM,
            recorded_at=timezone.make_aware(datetime.combine(date(2026, 1, day), time(9, 0))),
            recorded_by=nurse,
            bp_systolic=120, bp_diastolic=80, pulse=pulse,
            temperature=Decimal("98.6"), spo2=98, weight=weight,
        )

    r_jan5 = _reading(5, 70, weight=Decimal("60.0"))
    r_jan10 = _reading(10, 72)                    # no weight
    r_jan20 = _reading(20, 74, weight=Decimal("61.0"))
    return {"patient": patient, "readings": [r_jan5, r_jan10, r_jan20]}


def _ids(result):
    return [r["id"] for r in result["data"]["vitalHistory"]]


def test_returns_readings_sorted_by_recorded_at(admin_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    result = admin_client.execute(VITAL_HISTORY, {"patientId": pid})
    assert result.get("errors") is None
    expected = [str(r.id) for r in patient_with_readings["readings"]]  # Jan 5,10,20
    assert _ids(result) == expected


def test_date_range_filter(admin_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    result = admin_client.execute(
        VITAL_HISTORY,
        {"patientId": pid, "dateFrom": "2026-01-08", "dateTo": "2026-01-15"},
    )
    assert result.get("errors") is None
    # Only the Jan 10 reading falls in [Jan 8, Jan 15].
    jan10 = str(patient_with_readings["readings"][1].id)
    assert _ids(result) == [jan10]


def test_date_to_is_inclusive(admin_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    # dateTo == the Jan 20 reading's day; it should be included.
    result = admin_client.execute(
        VITAL_HISTORY, {"patientId": pid, "dateFrom": "2026-01-20", "dateTo": "2026-01-20"}
    )
    jan20 = str(patient_with_readings["readings"][2].id)
    assert _ids(result) == [jan20]


def test_type_filter_weight(admin_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    # Only readings that recorded a weight (Jan 5 and Jan 20).
    result = admin_client.execute(
        VITAL_HISTORY, {"patientId": pid, "types": ["WEIGHT"]}
    )
    assert result.get("errors") is None
    r = patient_with_readings["readings"]
    assert _ids(result) == [str(r[0].id), str(r[2].id)]


def test_nurse_role_allowed(nurse_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    result = nurse_client.execute(VITAL_HISTORY, {"patientId": pid})
    assert result.get("errors") is None
    assert len(result["data"]["vitalHistory"]) == 3


def test_finance_role_rejected(finance_client, patient_with_readings):
    pid = str(patient_with_readings["patient"].id)
    result = finance_client.execute(VITAL_HISTORY, {"patientId": pid})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
