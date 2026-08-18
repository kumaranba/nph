"""Tests for the dashboard queries."""
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from api.models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    ChargeCategory,
    Fee,
    Invoice,
    InvoiceStatus,
    Patient,
    Payment,
    Room,
    User,
    UserRole,
    VitalReading,
    VitalSession,
    VitalsThreshold,
    VitalType,
)


@pytest.fixture
def seeded(db):
    """A small but complete dataset: room/beds, an active admission, an
    outstanding invoice with a partial payment, a charge, and a flagged
    reading breaching SpO2 (critical) and pulse (warning)."""
    room = Room.objects.create(name="Ward A", capacity=3)
    b1 = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    Bed.objects.create(room=room, label="A2", status=BedStatus.VACANT)

    VitalsThreshold.objects.create(
        vital_type=VitalType.SPO2, below_threshold=Decimal("90"), above_threshold=None
    )
    VitalsThreshold.objects.create(
        vital_type=VitalType.PULSE, below_threshold=Decimal("50"),
        above_threshold=Decimal("120"),
    )

    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="Pneumonia", admitting_doctor="Dr. X"
    )
    admission = Admission.objects.create(
        patient=patient, bed=b1, admission_date=date(2026, 1, 15),
        monthly_fee=Decimal("25000.00"), status=AdmissionStatus.ACTIVE,
    )
    nurse = User.objects.create_user(
        email="rn@dash.test", password="secret123", role=UserRole.NURSE
    )
    finance = User.objects.create_user(
        email="fin@dash.test", password="secret123", role=UserRole.FINANCE
    )

    fee = Fee.objects.create(
        admission=admission, amount=Decimal("25000.00"),
        effective_from=date(2026, 1, 15), is_active=True, reason="test",
    )
    invoice = Invoice.objects.create(
        admission=admission, fee=fee,
        billing_period_start=date(2026, 1, 15), billing_period_end=date(2026, 2, 14),
        base_fee=Decimal("25000.00"), total_due=Decimal("25000.00"),
        status=InvoiceStatus.PARTIAL,
    )
    Payment.objects.create(
        invoice=invoice, amount=Decimal("10000.00"),
        paid_on=date(2026, 1, 20), recorded_by=finance,
    )
    AdditionalCharge.objects.create(
        admission=admission, category=ChargeCategory.DRUGS, amount=Decimal("500"),
        charge_date=date(2026, 1, 18), recorded_by=finance,
    )
    reading = VitalReading.objects.create(
        admission=admission, session=VitalSession.AM,
        recorded_at=timezone.make_aware(datetime.combine(date(2026, 1, 21), time(9))),
        recorded_by=nurse, bp_systolic=120, bp_diastolic=80, pulse=130,
        temperature=Decimal("98.6"), spo2=80,
    )
    reading.has_flag = True
    reading.save(update_fields=["has_flag"])
    return {"admission": admission, "invoice": invoice}


STATS = """
query { dashboardStats {
  bedsOccupied bedsTotal outstandingTotal outstandingInvoiceCount overdueCount
  feesDueTotal feesDueCount feesDueToday
  flaggedVitalsCount flaggedPatientCount criticalCount
} }
"""


def test_dashboard_stats(admin_client, seeded):
    result = admin_client.execute(STATS)
    assert result.get("errors") is None
    s = result["data"]["dashboardStats"]
    assert s["bedsOccupied"] == 1
    assert s["bedsTotal"] == 2
    # 25000 due - 10000 paid = 15000 outstanding.
    assert Decimal(str(s["outstandingTotal"])) == Decimal("15000.00")
    assert s["outstandingInvoiceCount"] == 1
    # The reading breaches two vitals (SpO2 + pulse) — counted per measurement.
    assert s["flaggedVitalsCount"] == 2
    assert s["flaggedPatientCount"] == 1
    # SpO2 80 (<90 by >10%) is critical; pulse 130 (>120 by <10%) is a warning.
    assert s["criticalCount"] == 1


def test_dashboard_stats_any_role(nurse_client, seeded):
    assert nurse_client.execute(STATS).get("errors") is None


FLAGGED = "query { flaggedVitals { id patientName room vital value direction severity } }"


def test_flagged_vitals_feed(nurse_client, seeded):
    result = nurse_client.execute(FLAGGED)
    assert result.get("errors") is None
    items = result["data"]["flaggedVitals"]
    vitals_by_name = {i["vital"]: i for i in items}
    assert "SpO₂" in vitals_by_name
    assert vitals_by_name["SpO₂"]["direction"] == "low"
    assert vitals_by_name["SpO₂"]["severity"] == "critical"
    assert vitals_by_name["Pulse"]["direction"] == "high"


def test_flagged_vitals_finance_rejected(finance_client, seeded):
    result = finance_client.execute(FLAGGED)
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


TREND = "query { paymentsTrend(months: 3) { month total } }"


def test_payments_trend_finance_ok_nurse_rejected(finance_client, nurse_client, seeded):
    ok = finance_client.execute(TREND)
    assert ok.get("errors") is None
    assert len(ok["data"]["paymentsTrend"]) == 3

    denied = nurse_client.execute(TREND)
    assert denied["data"] is None
    assert "Permission denied" in denied["errors"][0]["message"]


def test_recent_admissions(admin_client, seeded):
    q = "query { recentAdmissions(limit: 5) { id admittingDoctor patient { name } bed { label room { name } } } }"
    result = admin_client.execute(q)
    assert result.get("errors") is None
    rows = result["data"]["recentAdmissions"]
    assert rows[0]["patient"]["name"] == "Jane Doe"
    assert rows[0]["admittingDoctor"] == "Dr. X"   # passthrough from patient
    assert rows[0]["bed"]["room"]["name"] == "Ward A"


def test_wards(admin_client, seeded):
    result = admin_client.execute("query { wards { id name beds { label status } } }")
    assert result.get("errors") is None
    ward = result["data"]["wards"][0]
    assert ward["name"] == "Ward A"
    assert len(ward["beds"]) == 2


def test_activity_log(admin_client, seeded):
    result = admin_client.execute(
        "query { activityLog(limit: 10) { id kind message actor createdAt } }"
    )
    assert result.get("errors") is None
    kinds = {a["kind"] for a in result["data"]["activityLog"]}
    # Synthesized from multiple sources.
    assert {"payment", "admission", "charge", "vitals"} <= kinds
