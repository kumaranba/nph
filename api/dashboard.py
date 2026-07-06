"""Aggregations powering the dashboard widgets.

Everything here is derived from existing operational data — there is no
separate analytics/audit store. The activity feed is synthesized from recent
records across payments, admissions, charges and flagged vitals.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from . import vitals
from .billing import BillingService
from .models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    InvoiceStatus,
    Payment,
    VitalReading,
)

_OUTSTANDING = [InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]


# --------------------------------------------------------------------- vitals
def _active_flagged_readings():
    """Flagged readings for currently-admitted patients, newest first."""
    return (
        VitalReading.objects.filter(
            has_flag=True, admission__status=AdmissionStatus.ACTIVE
        )
        .select_related("admission__patient", "admission__bed__room")
        .order_by("-recorded_at")
    )


def flagged_vital_items(limit: int | None = None) -> list[dict]:
    """One item per out-of-range vital on each active flagged reading."""
    items: list[dict] = []
    for reading in _active_flagged_readings():
        patient = reading.admission.patient
        room = reading.admission.bed.room.name
        for breach in vitals.breach_details(reading):
            items.append(
                {
                    "id": f"{reading.id}:{breach['vital_type']}",
                    "patient_name": patient.name,
                    "room": room,
                    "vital": breach["label"],
                    "value": breach["value"],
                    "direction": breach["direction"],
                    "severity": breach["severity"],
                    "recorded_at": reading.recorded_at,
                }
            )
    if limit is not None:
        items = items[:limit]
    return items


# -------------------------------------------------------------------- billing
def _outstanding_total() -> Decimal:
    from .models import Invoice

    total = Decimal("0")
    for inv in Invoice.objects.filter(status__in=_OUTSTANDING).prefetch_related(
        "payments"
    ):
        paid = inv.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        total += inv.total_due - (inv.refund_amount or Decimal("0")) - paid
    return total


def _fees_due():
    """(count, total, due_today) for active admissions billing within the
    configured warning window."""
    today = date.today()
    window = settings.FEE_DUE_WARNING_DAYS
    count = 0
    total = Decimal("0")
    due_today = 0
    for admission in Admission.objects.filter(status=AdmissionStatus.ACTIVE):
        if today < admission.admission_date:
            continue
        due = BillingService.next_billing_cycle_date(admission.admission_date, today)
        days = (due - today).days
        if days > window:
            continue
        count += 1
        total += admission.monthly_fee
        if days == 0:
            due_today += 1
    return count, total, due_today


def compute_stats() -> dict:
    from .models import Invoice

    today = date.today()
    flagged = flagged_vital_items()
    fees_count, fees_total, fees_today = _fees_due()

    return {
        "beds_occupied": Bed.objects.filter(status=BedStatus.OCCUPIED).count(),
        "beds_total": Bed.objects.count(),
        "outstanding_total": _outstanding_total(),
        "outstanding_invoice_count": Invoice.objects.filter(
            status__in=_OUTSTANDING
        ).count(),
        "overdue_count": Invoice.objects.filter(
            status__in=_OUTSTANDING, billing_period_end__lt=today
        ).count(),
        "fees_due_total": fees_total,
        "fees_due_count": fees_count,
        "fees_due_today": fees_today,
        "flagged_vitals_count": len(flagged),
        "flagged_patient_count": len({f["patient_name"] for f in flagged}),
        "critical_count": sum(1 for f in flagged if f["severity"] == "critical"),
    }


# ------------------------------------------------------------- payments trend
def payments_trend(months: int = 6) -> list[dict]:
    """Total payments per month for the last `months` months, oldest first."""
    today = date.today()
    buckets: list[dict] = []
    year, month = today.year, today.month
    seq = []
    for _ in range(months):
        seq.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    for y, m in reversed(seq):
        total = (
            Payment.objects.filter(paid_on__year=y, paid_on__month=m).aggregate(
                t=Sum("amount")
            )["t"]
            or Decimal("0")
        )
        buckets.append({"month": date(y, m, 1).strftime("%b"), "total": total})
    return buckets


# --------------------------------------------------------------- activity feed
def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    # A plain date — anchor at midnight in the current timezone.
    return timezone.make_aware(datetime.combine(value, time.min)).isoformat()


def _sort_key(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return timezone.make_aware(datetime.combine(value, time.min))


def activity_items(limit: int = 10) -> list[dict]:
    """Recent activity synthesized from payments, admissions, charges and
    flagged vitals, newest first."""
    events: list[tuple] = []  # (sort_dt, item)

    for p in Payment.objects.select_related(
        "recorded_by", "invoice__admission__patient"
    ).order_by("-paid_on")[:limit]:
        patient = p.invoice.admission.patient
        events.append(
            (
                _sort_key(p.paid_on),
                {
                    "id": f"payment:{p.id}",
                    "kind": "payment",
                    "message": f"Payment of ₹{p.amount} for {patient.name}",
                    "actor": p.recorded_by.email if p.recorded_by else "—",
                    "created_at": _iso(p.paid_on),
                },
            )
        )

    for a in Admission.objects.select_related("patient", "bed__room").order_by(
        "-admission_date"
    )[:limit]:
        events.append(
            (
                _sort_key(a.admission_date),
                {
                    "id": f"admission:{a.id}",
                    "kind": "admission",
                    "message": f"{a.patient.name} admitted to "
                    f"{a.bed.room.name} {a.bed.label}",
                    "actor": "—",
                    "created_at": _iso(a.admission_date),
                },
            )
        )

    for c in AdditionalCharge.objects.select_related(
        "recorded_by", "admission__patient"
    ).order_by("-charge_date")[:limit]:
        events.append(
            (
                _sort_key(c.charge_date),
                {
                    "id": f"charge:{c.id}",
                    "kind": "charge",
                    "message": f"{c.get_category_display()} charge of ₹{c.amount} "
                    f"for {c.admission.patient.name}",
                    "actor": c.recorded_by.email if c.recorded_by else "—",
                    "created_at": _iso(c.charge_date),
                },
            )
        )

    for r in _active_flagged_readings()[:limit]:
        events.append(
            (
                _sort_key(r.recorded_at),
                {
                    "id": f"vitals:{r.id}",
                    "kind": "vitals",
                    "message": f"Flagged vitals for {r.admission.patient.name}",
                    "actor": r.recorded_by.email if r.recorded_by else "—",
                    "created_at": _iso(r.recorded_at),
                },
            )
        )

    events.sort(key=lambda e: e[0], reverse=True)
    return [item for _, item in events[:limit]]
