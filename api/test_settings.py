"""Tests for the systemSettings query and updateSettings mutation (Admin only)."""
from decimal import Decimal

from api.models import SystemSetting, VitalsThreshold, VitalType

SYSTEM_SETTINGS = """
query {
  systemSettings {
    feeDueWarningDays
    vitalsThresholds { vitalType belowThreshold aboveThreshold }
  }
}
"""

UPDATE_SETTINGS = """
mutation Update($feeDueWarningDays: Int, $thresholds: [VitalsThresholdInput!]) {
  updateSettings(feeDueWarningDays: $feeDueWarningDays, thresholds: $thresholds) {
    feeDueWarningDays
    vitalsThresholds { vitalType belowThreshold aboveThreshold }
  }
}
"""


def test_admin_can_read_system_settings(admin_client, db):
    VitalsThreshold.objects.create(
        vital_type=VitalType.SPO2, below_threshold=Decimal("90"), above_threshold=None
    )
    result = admin_client.execute(SYSTEM_SETTINGS)
    assert result.get("errors") is None
    data = result["data"]["systemSettings"]
    # Defaults from the env-seeded SystemSetting (7).
    assert data["feeDueWarningDays"] == 7
    assert any(t["vitalType"] == "SPO2" for t in data["vitalsThresholds"])


def test_nurse_cannot_read_system_settings(nurse_client):
    result = nurse_client.execute(SYSTEM_SETTINGS)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_finance_cannot_read_system_settings(finance_client):
    result = finance_client.execute(SYSTEM_SETTINGS)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_admin_updates_fee_due_warning_days(admin_client, db):
    result = admin_client.execute(UPDATE_SETTINGS, {"feeDueWarningDays": 14})
    assert result.get("errors") is None
    assert result["data"]["updateSettings"]["feeDueWarningDays"] == 14
    # Persisted to the singleton.
    assert SystemSetting.load().fee_due_warning_days == 14


def test_admin_upserts_vitals_thresholds(admin_client, db):
    result = admin_client.execute(
        UPDATE_SETTINGS,
        {
            "thresholds": [
                {"vitalType": "PULSE", "belowThreshold": "50", "aboveThreshold": "120"},
                {"vitalType": "SPO2", "belowThreshold": "90", "aboveThreshold": None},
            ]
        },
    )
    assert result.get("errors") is None
    thresholds = {
        t["vitalType"]: t
        for t in result["data"]["updateSettings"]["vitalsThresholds"]
    }
    assert Decimal(str(thresholds["PULSE"]["aboveThreshold"])) == Decimal("120")
    assert thresholds["SPO2"]["aboveThreshold"] is None

    # A second update overwrites the existing row (upsert, not duplicate).
    admin_client.execute(
        UPDATE_SETTINGS,
        {"thresholds": [{"vitalType": "PULSE", "belowThreshold": "55", "aboveThreshold": "110"}]},
    )
    pulse = VitalsThreshold.objects.get(vital_type=VitalType.PULSE)
    assert pulse.below_threshold == Decimal("55.00")
    assert pulse.above_threshold == Decimal("110.00")
    assert VitalsThreshold.objects.filter(vital_type=VitalType.PULSE).count() == 1


def test_nurse_cannot_update_settings(nurse_client, db):
    result = nurse_client.execute(UPDATE_SETTINGS, {"feeDueWarningDays": 99})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    # Unchanged.
    assert SystemSetting.load().fee_due_warning_days == 7


def test_update_rejects_negative_fee_days(admin_client, db):
    result = admin_client.execute(UPDATE_SETTINGS, {"feeDueWarningDays": -1})
    assert result["data"] is None
    assert "non-negative" in result["errors"][0]["message"]
