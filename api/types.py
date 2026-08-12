from datetime import date
from decimal import Decimal
from typing import Optional

import strawberry
import strawberry_django
from django.db.models import Sum
from strawberry import auto
from . import models
from .models import InvoiceStatus

# Invoice statuses that count as money still owed.
_OUTSTANDING_STATUSES = [InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]


@strawberry_django.type(models.User)
class UserType:
    id: auto
    email: auto
    role: auto
    is_active: auto
    date_joined: auto


@strawberry_django.type(models.Room)
class RoomType:
    id: auto
    name: auto
    capacity: auto
    beds: list['BedType']


@strawberry_django.type(models.Bed)
class BedType:
    id: auto
    room: RoomType
    label: auto
    status: auto


@strawberry_django.type(models.Tag)
class TagType:
    id: auto
    name: auto
    label: auto
    category: auto

    # Number of patients carrying this tag (drives suggestion ranking).
    @strawberry.field
    def patient_count(self) -> int:
        return self.patients.count()


@strawberry_django.type(models.Patient)
class PatientType:
    id: auto
    patient_id: auto
    name: auto
    age: auto
    gender: auto
    diagnosis: auto
    guardian_name: auto
    guardian_phone: auto
    admitting_doctor: auto
    created_at: auto
    admissions: list['AdmissionType']

    # Tags applied to this patient, alphabetical.
    @strawberry.field
    def tags(self) -> list['TagType']:
        return self.tags.order_by('name')


@strawberry_django.type(models.Admission)
class AdmissionType:
    id: auto
    patient: PatientType
    bed: Optional[BedType]
    admission_date: auto
    monthly_fee: auto
    status: auto
    discharge_date: auto
    discharge_type: auto
    discharge_notes: auto
    refund_amount: auto
    credit_balance: auto

    # Outstanding-dues info, computed from the admission's invoices. Lets the
    # UI warn about unpaid balances before a discharge is confirmed.
    @strawberry.field
    def outstanding_invoice_count(self) -> int:
        return self.invoices.filter(status__in=_OUTSTANDING_STATUSES).count()

    @strawberry.field
    def has_outstanding_dues(self) -> bool:
        return self.invoices.filter(status__in=_OUTSTANDING_STATUSES).exists()

    # Charge log for this admission, most recent first.
    @strawberry.field
    def additional_charges(self) -> list['AdditionalChargeType']:
        return self.additional_charges.order_by('-charge_date', '-id')

    # Convenience passthrough of the patient's admitting doctor.
    @strawberry.field
    def admitting_doctor(self) -> str:
        return self.patient.admitting_doctor

    # The admission's currently-active fee, if any.
    @strawberry.field
    def active_fee(self) -> Optional['FeeType']:
        return self.fees.filter(is_active=True).first()

    # Default effective date for a fee change (next not-yet-invoiced cycle).
    @strawberry.field
    def next_fee_cycle_date(self) -> date:
        from .fees import FeeService
        return FeeService.next_uninvoiced_cycle(self)


@strawberry_django.type(models.Fee)
class FeeType:
    id: auto
    admission: AdmissionType
    amount: auto
    effective_from: auto
    is_active: auto
    reason: auto
    created_by: Optional[UserType]
    created_at: auto
    deactivated_at: auto


@strawberry_django.type(models.Invoice)
class InvoiceType:
    id: auto
    admission: AdmissionType
    fee: Optional['FeeType']
    billing_period_start: auto
    billing_period_end: auto
    base_fee: auto
    refund_amount: auto
    total_due: auto
    status: auto

    # The charge line items billed in this invoice's period.
    @strawberry.field
    def additional_charges(self) -> list['AdditionalChargeType']:
        return self.admission.additional_charges.filter(
            charge_date__gte=self.billing_period_start,
            charge_date__lte=self.billing_period_end,
        ).order_by('charge_date')

    # Payment history against this invoice, oldest first.
    @strawberry.field
    def payments(self) -> list['PaymentType']:
        return self.payments.order_by('paid_on')

    @strawberry.field
    def amount_paid(self) -> Decimal:
        return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    @strawberry.field
    def balance_due(self) -> Decimal:
        paid = self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return self.total_due - (self.refund_amount or Decimal('0')) - paid


@strawberry_django.type(models.Payment)
class PaymentType:
    id: auto
    invoice: InvoiceType
    amount: auto
    paid_on: auto
    recorded_by: UserType


@strawberry_django.type(models.AdditionalCharge)
class AdditionalChargeType:
    id: auto
    admission: AdmissionType
    category: auto
    amount: auto
    charge_date: auto
    description: auto
    recorded_by: UserType


@strawberry_django.type(models.VitalReading)
class VitalReadingType:
    id: auto
    admission: AdmissionType
    session: auto
    recorded_at: auto
    recorded_by: UserType
    bp_systolic: auto
    bp_diastolic: auto
    pulse: auto
    temperature: auto
    spo2: auto
    weight: auto
    notes: auto
    has_flag: auto

    # The specific vitals that breached a threshold (e.g. ["SPO2", "PULSE"]),
    # so the UI can say which reading is out of range.
    @strawberry.field
    def flagged_vitals(self) -> list[str]:
        from .vitals import breached_vitals
        return breached_vitals(self)


@strawberry_django.type(models.VitalsThreshold)
class VitalsThresholdType:
    id: auto
    vital_type: auto
    below_threshold: auto
    above_threshold: auto
