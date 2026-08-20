"""Canteen meal count — a monthly report combining patient and staff meals.

For each day of a month:
  * **Patient count** = patients admitted that day (both boundary days
    inclusive), split by ``Patient.gender``. On **Wednesday & Sunday** both
    menus are served, so patients split Veg / Non-Veg by ``food_preference``
    (blank → Veg). Every other day is Veg-only.
  * **Staff count** = staff present that day (attendance PRESENT or HALF_DAY),
    split by staff gender. Staff is never veg-split.

Costs (monthly):
  * **Patient** = sum over days of (patients that day × the day's ``FoodRate``).
  * **Staff** = number of ACTIVE staff × the ``StaffMealRate`` in force (flat
    per active staff, per the agreed rule — independent of attendance).

Counting caps at today so an ongoing month never counts future days.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from .models import (
    Admission,
    Attendance,
    AttendanceStatus,
    FoodPreference,
    FoodRate,
    Gender,
    Staff,
    StaffMealRate,
)

# Weekday indexes (Python weekday(): Mon=0 … Sun=6) that serve both menus.
_SPLIT_WEEKDAYS = {2, 6}   # Wednesday, Sunday
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_PRESENT = [AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY]


def _gender_key(value):
    """Map a stored gender to one of male/female/other (blank → other)."""
    if value == Gender.MALE:
        return "male"
    if value == Gender.FEMALE:
        return "female"
    return "other"


@dataclass
class CanteenDay:
    day: date
    dow: str
    is_split: bool
    # Patient counts by gender; *_nonveg is the non-veg portion (0 on non-split
    # days, where everyone is served veg).
    male_patients: int = 0
    male_patients_nonveg: int = 0
    female_patients: int = 0
    female_patients_nonveg: int = 0
    other_patients: int = 0
    other_patients_nonveg: int = 0
    # Staff counts by gender (single count, no veg split).
    male_staff: int = 0
    female_staff: int = 0
    other_staff: int = 0

    @property
    def patients(self):
        return self.male_patients + self.female_patients + self.other_patients

    @property
    def staff(self):
        return self.male_staff + self.female_staff + self.other_staff

    @property
    def total(self):
        return self.patients + self.staff


@dataclass
class CanteenTotals:
    male_patients: int = 0
    male_patients_nonveg: int = 0
    female_patients: int = 0
    female_patients_nonveg: int = 0
    other_patients: int = 0
    other_patients_nonveg: int = 0
    male_staff: int = 0
    female_staff: int = 0
    other_staff: int = 0
    patient_days: int = 0
    staff_days: int = 0

    @property
    def total(self):
        return self.patient_days + self.staff_days


@dataclass
class CanteenReport:
    month: str                       # 'YYYY-MM'
    daily_rate: Decimal              # patient per-day food rate (reference)
    staff_monthly_rate: Decimal      # staff monthly meal rate (reference)
    active_staff: int
    days: list = field(default_factory=list)
    totals: CanteenTotals = field(default_factory=CanteenTotals)
    patient_cost: Decimal = Decimal("0")
    staff_cost: Decimal = Decimal("0")
    grand_total_cost: Decimal = Decimal("0")
    # Whether any Other-gender patient/staff appeared (so the UI can hide the
    # Other columns when everyone is Male/Female).
    has_other: bool = False


def _month_bounds(month, today):
    if month:
        year, mon = (int(p) for p in month.split("-"))
    else:
        year, mon = today.year, today.month
    first = date(year, mon, 1)
    last = date(year, mon, monthrange(year, mon)[1])
    return first, last


def _rate_for(rates, day):
    """Amount from a list of FoodRate ordered by -effective_from, for ``day``."""
    for r in rates:
        if r.effective_from <= day:
            return r.amount
    return Decimal("0")


def build_canteen_report(month=None, today=None):
    today = today or date.today()
    first, last = _month_bounds(month, today)
    end = min(last, today)

    # Pull the month's data once, then compute per day in Python.
    admissions = list(
        Admission.objects
        .select_related("patient")
        .filter(admission_date__lte=last)
        .filter(Q(discharge_date__isnull=True) | Q(discharge_date__gte=first))
    )
    attendance = list(
        Attendance.objects
        .select_related("staff")
        .filter(date__gte=first, date__lte=end, status__in=_PRESENT)
    )
    att_by_day = {}
    for a in attendance:
        att_by_day.setdefault(a.date, []).append(a.staff)

    food_rates = list(FoodRate.objects.all())          # ordered -effective_from
    daily_rate = _rate_for(food_rates, end) if food_rates else Decimal("0")
    staff_rate_obj = StaffMealRate.rate_on(end)
    staff_rate = staff_rate_obj.amount if staff_rate_obj else Decimal("0")
    active_staff = Staff.objects.filter(is_active=True).count()

    report = CanteenReport(
        month=first.strftime("%Y-%m"),
        daily_rate=daily_rate,
        staff_monthly_rate=staff_rate,
        active_staff=active_staff,
    )
    totals = report.totals
    patient_cost = Decimal("0")

    day = first
    while day <= end:
        is_split = day.weekday() in _SPLIT_WEEKDAYS
        cd = CanteenDay(day=day, dow=_DOW[day.weekday()], is_split=is_split)

        present_patients = 0
        for adm in admissions:
            if adm.admission_date > day:
                continue
            if adm.discharge_date is not None and adm.discharge_date < day:
                continue
            present_patients += 1
            gk = _gender_key(adm.patient.gender)
            nonveg = is_split and adm.patient.food_preference == FoodPreference.NON_VEG
            if gk == "male":
                cd.male_patients += 1
                if nonveg:
                    cd.male_patients_nonveg += 1
            elif gk == "female":
                cd.female_patients += 1
                if nonveg:
                    cd.female_patients_nonveg += 1
            else:
                cd.other_patients += 1
                if nonveg:
                    cd.other_patients_nonveg += 1

        for staff in att_by_day.get(day, []):
            gk = _gender_key(staff.gender)
            if gk == "male":
                cd.male_staff += 1
            elif gk == "female":
                cd.female_staff += 1
            else:
                cd.other_staff += 1

        # Accumulate totals.
        totals.male_patients += cd.male_patients
        totals.male_patients_nonveg += cd.male_patients_nonveg
        totals.female_patients += cd.female_patients
        totals.female_patients_nonveg += cd.female_patients_nonveg
        totals.other_patients += cd.other_patients
        totals.other_patients_nonveg += cd.other_patients_nonveg
        totals.male_staff += cd.male_staff
        totals.female_staff += cd.female_staff
        totals.other_staff += cd.other_staff
        totals.patient_days += cd.patients
        totals.staff_days += cd.staff

        patient_cost += present_patients * _rate_for(food_rates, day)
        if cd.other_patients or cd.other_staff:
            report.has_other = True

        report.days.append(cd)
        day += timedelta(days=1)

    report.patient_cost = patient_cost
    report.staff_cost = active_staff * staff_rate
    report.grand_total_cost = report.patient_cost + report.staff_cost
    return report
