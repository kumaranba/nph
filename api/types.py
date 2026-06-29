import strawberry
import strawberry_django
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


@strawberry_django.type(models.Patient)
class PatientType:
    id: auto
    patient_id: auto
    name: auto
    age: auto
    diagnosis: auto
    guardian_name: auto
    guardian_phone: auto
    admitting_doctor: auto
    created_at: auto
    admissions: list['AdmissionType']


@strawberry_django.type(models.Admission)
class AdmissionType:
    id: auto
    patient: PatientType
    bed: BedType
    admission_date: auto
    monthly_fee: auto
    status: auto
    discharge_date: auto
    discharge_type: auto
    discharge_notes: auto
    refund_amount: auto

    # Outstanding-dues info, computed from the admission's invoices. Lets the
    # UI warn about unpaid balances before a discharge is confirmed.
    @strawberry.field
    def outstanding_invoice_count(self) -> int:
        return self.invoices.filter(status__in=_OUTSTANDING_STATUSES).count()

    @strawberry.field
    def has_outstanding_dues(self) -> bool:
        return self.invoices.filter(status__in=_OUTSTANDING_STATUSES).exists()


@strawberry_django.type(models.Invoice)
class InvoiceType:
    id: auto
    admission: AdmissionType
    billing_period_start: auto
    billing_period_end: auto
    base_fee: auto
    refund_amount: auto
    total_due: auto
    status: auto


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


@strawberry_django.type(models.VitalsThreshold)
class VitalsThresholdType:
    id: auto
    vital_type: auto
    below_threshold: auto
    above_threshold: auto
