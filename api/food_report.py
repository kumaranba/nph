"""Food reports built from admissions and the effective-dated FoodRate.

Two reports, both priced at the flat per-patient-day FoodRate and counting a
patient-day for **every calendar day from admission through discharge,
inclusive of both boundary days** (see CLAUDE.md / the food-vendor rules):

1. ``build_food_vendor_list`` — the daily vendor payment list: for each day in
   a range, how many patients were present × that day's rate.
2. ``build_patient_food_report`` — a patient-wise monthly report, one row per
   admission overlapping the month, split into three groups:
     G1 discharged this month (incl. same-month admit+discharge),
     G2 newly admitted this month (and not discharged this month),
     G3 stayed the whole month (admitted earlier, not discharged this month).

Both cap counting at "today" so an ongoing month never counts future days.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from .models import Admission, FoodRate


# --- daily vendor payment list --------------------------------------------

@dataclass
class VendorDay:
    day: date
    patients: int
    rate: Decimal
    amount: Decimal


@dataclass
class VendorList:
    date_from: date
    date_to: date
    rows: list = field(default_factory=list)
    total_patient_days: int = 0
    total_amount: Decimal = Decimal("0")


def _present_on(day):
    """Admissions whose stay covers ``day`` (both boundary days inclusive)."""
    return Admission.objects.filter(
        admission_date__lte=day,
    ).filter(
        Q(discharge_date__isnull=True) | Q(discharge_date__gte=day)
    )


def build_food_vendor_list(date_from, date_to, today=None):
    """Daily patient-day counts × the day's food rate, over an inclusive range.
    The range end is clamped to today (no future days)."""
    today = today or date.today()
    end = min(date_to, today)
    out = VendorList(date_from=date_from, date_to=date_to)
    if end < date_from:
        return out

    day = date_from
    while day <= end:
        count = _present_on(day).count()
        rate_obj = FoodRate.rate_on(day)
        rate = rate_obj.amount if rate_obj else Decimal("0")
        amount = rate * count
        out.rows.append(VendorDay(day=day, patients=count, rate=rate, amount=amount))
        out.total_patient_days += count
        out.total_amount += amount
        day += timedelta(days=1)
    return out


# --- patient-wise monthly report ------------------------------------------

@dataclass
class PatientFoodRow:
    admission_id: int
    patient_pk: int
    patient_code: str
    name: str
    days: int
    rate: Decimal
    amount: Decimal


@dataclass
class PatientFoodGroup:
    key: str
    label: str
    rows: list = field(default_factory=list)
    total_days: int = 0
    total_amount: Decimal = Decimal("0")


@dataclass
class PatientFoodReport:
    month: str            # 'YYYY-MM'
    rate: Decimal         # reference rate/day used for the month
    groups: list = field(default_factory=list)
    grand_total_days: int = 0
    grand_total_amount: Decimal = Decimal("0")


def _month_bounds(month, today):
    """(first_day, last_day) for a 'YYYY-MM' string, defaulting to today's."""
    if month:
        year, mon = (int(p) for p in month.split("-"))
    else:
        year, mon = today.year, today.month
    first = date(year, mon, 1)
    last = date(year, mon, monthrange(year, mon)[1])
    return first, last


def build_patient_food_report(month=None, today=None):
    """Patient-wise food consumption for a calendar month, grouped."""
    today = today or date.today()
    first, last = _month_bounds(month, today)
    ref_date = min(last, today)          # don't count beyond today
    rate_obj = FoodRate.rate_on(ref_date)
    rate = rate_obj.amount if rate_obj else Decimal("0")

    groups = {
        "DISCHARGED": PatientFoodGroup("DISCHARGED", "Discharged this month"),
        "ADMITTED": PatientFoodGroup("ADMITTED", "Newly admitted this month"),
        "WHOLE_MONTH": PatientFoodGroup("WHOLE_MONTH", "Stayed the whole month"),
    }

    # Admissions overlapping the month: started on/before month end and not
    # discharged before the month started.
    admissions = (
        Admission.objects
        .select_related("patient")
        .filter(admission_date__lte=last)
        .filter(Q(discharge_date__isnull=True) | Q(discharge_date__gte=first))
        .order_by("patient__name", "id")
    )

    for adm in admissions:
        adm_date = adm.admission_date
        dis_date = adm.discharge_date

        discharged_this_month = dis_date is not None and first <= dis_date <= last
        admitted_this_month = first <= adm_date <= last

        if discharged_this_month:
            key = "DISCHARGED"
        elif admitted_this_month:
            key = "ADMITTED"
        elif adm_date < first and (dis_date is None or dis_date > last):
            key = "WHOLE_MONTH"
        else:
            continue      # not present during the month

        # Days consumed within the month (inclusive), capped at today.
        start = max(adm_date, first)
        present_end = dis_date if dis_date is not None else ref_date
        end = min(present_end, ref_date)
        days = (end - start).days + 1
        if days <= 0:
            continue
        amount = rate * days

        grp = groups[key]
        grp.rows.append(PatientFoodRow(
            admission_id=adm.id,
            patient_pk=adm.patient_id,
            patient_code=adm.patient.patient_id,
            name=adm.patient.name,
            days=days,
            rate=rate,
            amount=amount,
        ))
        grp.total_days += days
        grp.total_amount += amount

    report = PatientFoodReport(month=first.strftime("%Y-%m"), rate=rate)
    for key in ("DISCHARGED", "ADMITTED", "WHOLE_MONTH"):
        grp = groups[key]
        report.groups.append(grp)
        report.grand_total_days += grp.total_days
        report.grand_total_amount += grp.total_amount
    return report
