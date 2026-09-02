from datetime import date
from decimal import Decimal
from typing import Optional

import strawberry
import strawberry_django
from django.db.models import Sum
from strawberry import auto
from strawberry.permission import BasePermission
from strawberry.types import Info
from . import models
from .models import InvoiceStatus

# Invoice statuses that count as money still owed.
_OUTSTANDING_STATUSES = [InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]


class IsAdmin(BasePermission):
    """Field-level guard: only ADMIN may read the annotated field. A non-Admin
    gets a permission error (the field resolves to null with the error), not a
    silent empty value."""
    message = "Aadhar data is restricted to Admin."

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        user = getattr(info.context.request, 'user', None)
        return getattr(user, 'role', None) == models.UserRole.ADMIN


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
    date_of_birth: auto
    gender: auto
    diagnosis: auto
    food_preference: auto
    is_alive: auto
    date_of_expiry: auto
    guardian_name: auto
    guardian_phone: auto
    admitting_doctor: auto
    place: auto
    contact_consent: auto
    do_not_contact: auto
    created_at: auto
    admissions: list['AdmissionType']

    # Age in whole years, computed from date_of_birth; None (UI shows "–") when
    # DOB is unset. There is no stored age field any more.
    @strawberry.field
    def age(self) -> Optional[int]:
        return self.age

    # Aadhar number is ADMIN-only at the API layer: a non-Admin that queries it
    # directly gets a permission error, not a null/empty value.
    @strawberry.field(permission_classes=[IsAdmin])
    def aadhar_number(self) -> Optional[str]:
        return self.aadhar_number or ''

    # Patient photo URL (served from MEDIA), or None if no photo.
    @strawberry.field
    def photo_url(self) -> Optional[str]:
        return self.photo.url if self.photo else None

    # Aadhar scan URL — ADMIN-only, like the Aadhar number.
    @strawberry.field(permission_classes=[IsAdmin])
    def aadhar_scan_url(self) -> Optional[str]:
        return self.aadhar_scan.url if self.aadhar_scan else None

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
    opening_balance: auto

    # Unpaid remainder of the carried-forward opening balance (the imported
    # figure less any payments applied to it). 0 when fully paid or none.
    @strawberry.field
    def opening_balance_due(self) -> Decimal:
        from .billing import BillingService
        inv = self.invoices.filter(is_opening_balance=True).first()
        return BillingService.balance_due(inv) if inv is not None else Decimal('0')

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

    # The fee in force for this admission: the active fee while admitted, or the
    # last fee that was active at discharge (fees are never deleted, so it's the
    # newest row). None only if the admission never had a fee.
    @strawberry.field
    def effective_fee(self) -> Optional['FeeType']:
        active = self.fees.filter(is_active=True).first()
        if active is not None:
            return active
        return self.fees.order_by('-effective_from', '-created_at').first()

    # Total still owed on this admission across its unpaid/partial invoices.
    # A discharged admission reads 0 (discharge clears all dues).
    @strawberry.field
    def outstanding_due(self) -> Decimal:
        from .billing import BillingService
        return BillingService.total_pending_dues(self)

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
    is_opening_balance: auto

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


@strawberry_django.type(models.PaymentAccount)
class PaymentAccountType:
    id: auto
    name: auto
    is_active: auto


@strawberry_django.type(models.PaymentReceipt)
class PaymentReceiptType:
    id: auto
    paid_on: auto
    amount: auto
    fees_amount: auto
    charges_amount: auto
    account: Optional[PaymentAccountType]
    recorded_by: Optional[UserType]
    created_at: auto

    # Flattened patient info for the payments-history grid.
    @strawberry.field
    def patient_pk(self) -> strawberry.ID:
        return self.admission.patient_id

    @strawberry.field
    def patient_name(self) -> str:
        return self.admission.patient.name

    @strawberry.field
    def patient_code(self) -> str:
        return self.admission.patient.patient_id


@strawberry_django.type(models.Payment)
class PaymentType:
    id: auto
    invoice: InvoiceType
    amount: auto
    paid_on: auto
    recorded_by: Optional[UserType]


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


@strawberry_django.type(models.Inquiry)
class InquiryType:
    id: auto
    name: auto
    phone: auto
    source: auto
    status: auto
    lost_reason: auto
    lost_reason_note: auto
    contact_consent: auto
    do_not_contact: auto
    consulted_on: auto
    notes: auto
    assigned_to: Optional[UserType]
    referrer: Optional["ReferrerType"]
    patient: Optional[PatientType]
    created_by: Optional[UserType]
    created_at: auto
    updated_at: auto


@strawberry_django.type(models.Referrer)
class ReferrerType:
    id: auto
    name: auto
    kind: auto
    organization: auto
    phone: auto
    email: auto
    notes: auto
    is_active: auto
    created_by: Optional[UserType]
    created_at: auto
    updated_at: auto


@strawberry_django.type(models.Activity)
class ActivityType:
    id: auto
    type: auto
    body: auto
    outcome: auto
    inquiry: Optional["InquiryType"]
    patient: Optional[PatientType]
    created_by: Optional[UserType]
    created_at: auto


@strawberry_django.type(models.Staff)
class StaffType:
    id: auto
    staff_code: auto
    name: auto
    designation: auto
    gender: auto
    phone: auto
    is_active: auto
    joined_on: auto
    user: Optional[UserType]
    created_at: auto


@strawberry_django.type(models.StaffMealRate)
class StaffMealRateType:
    id: auto
    amount: auto
    effective_from: auto
    note: auto
    created_by: Optional[UserType]
    created_at: auto


@strawberry_django.type(models.FoodRate)
class FoodRateType:
    id: auto
    amount: auto
    effective_from: auto
    note: auto
    created_by: Optional[UserType]
    created_at: auto


@strawberry_django.type(models.Attendance)
class AttendanceType:
    id: auto
    staff: StaffType
    date: auto
    status: auto
    recorded_by: Optional[UserType]
    created_at: auto
    updated_at: auto


@strawberry_django.type(models.FollowUp)
class FollowUpType:
    id: auto
    patient: Optional[PatientType]
    inquiry: Optional["InquiryType"]
    admission: Optional[AdmissionType]
    kind: auto
    note: auto
    follow_up_date: auto
    is_done: auto
    created_by: Optional[UserType]
    created_at: auto

    # A display name for the follow-up's subject (patient or lead).
    @strawberry.field
    def subject_name(self) -> str:
        return self.subject_name
