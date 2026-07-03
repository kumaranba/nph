from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional

import strawberry
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from graphql import GraphQLError
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

from . import auth
from .billing import BillingService
from .models import (
    AdditionalCharge, Admission, AdmissionStatus, Bed, BedStatus, Invoice,
    InvoiceStatus, Patient, Payment, Room, User, UserRole, VitalReading,
    VitalsThreshold,
)
from .permissions import login_required, require_roles
from .types import (
    AdditionalChargeType, AdmissionType, BedType, InvoiceType, PatientType,
    PaymentType, RoomType, UserType, VitalReadingType, VitalsThresholdType,
)


# ---------------------------------------------------------------------------
# Auth payload
# ---------------------------------------------------------------------------

@strawberry.enum
class ChargeCategoryEnum(Enum):
    """GraphQL enum for AdditionalCharge.category (mirrors models.ChargeCategory)."""
    DRUGS = 'DRUGS'
    SNACKS = 'SNACKS'
    PERSONAL_CARE = 'PERSONAL_CARE'
    SPECIALIST = 'SPECIALIST'
    OTHER = 'OTHER'


@strawberry.type
class AuthTokens:
    access_token: str
    refresh_token: str


@strawberry.type
class DischargeResult:
    """Outcome of a discharge.

    ``has_outstanding_dues`` is the warning flag the UI surfaces in red when
    the patient still has unpaid or partially-paid invoices at discharge time.
    """
    admission: 'AdmissionType'
    has_outstanding_dues: bool
    outstanding_invoice_count: int
    refund_amount: Decimal


@strawberry.input
class CreateAdmissionInput:
    """Everything needed to register a new patient and admit them to a bed.

    The patient record is created as part of the same operation, so callers
    pass the patient's details inline rather than an existing patient id.
    """
    # Patient details
    name: str
    age: int
    diagnosis: str
    admitting_doctor: str
    # Admission details
    bed_id: strawberry.ID
    admission_date: date
    monthly_fee: Decimal
    # Optional patient details
    guardian_name: Optional[str] = ""
    guardian_phone: Optional[str] = ""


# Number of days before an invoice's period end that we flag it "due soon".
DUE_SOON_WINDOW_DAYS = 7


def _today() -> date:
    """Indirection so tests can pin "today" deterministically."""
    return date.today()


@strawberry.type
class FeeDueItem:
    """A patient with an upcoming billing cycle date, for the fees-due list."""
    id: strawberry.ID          # patient primary key (for navigation)
    patient_id: str            # NPH-YYYY-NNNN code
    name: str
    room: Optional[str]
    due_date: date
    amount_due: Decimal
    days_until_due: int


@strawberry.type
class PatientSearchResult:
    """A flattened patient row for the search results table.

    ``admission_date``/``room``/``bed`` come from the patient's current (or
    most recent) admission; ``fee_status`` is derived from their latest
    invoice and is one of CURRENT / DUE_SOON / OVERDUE.
    """
    id: strawberry.ID
    patient_id: str
    name: str
    guardian_name: str
    guardian_phone: str
    admission_date: Optional[date]
    room: Optional[str]
    bed: Optional[str]
    fee_status: str


def _fee_status_for_patient(patient) -> str:
    """Derive a fee status from the patient's latest invoice.

    No invoice or a fully-paid latest invoice is CURRENT. Otherwise an unpaid
    or partial invoice is OVERDUE once its billing period has ended, DUE_SOON
    within the next week, and CURRENT before that.
    """
    invoice = (
        Invoice.objects.filter(admission__patient=patient)
        .order_by('-billing_period_end')
        .first()
    )
    if invoice is None or invoice.status == InvoiceStatus.PAID:
        return 'CURRENT'

    today = date.today()
    if invoice.billing_period_end < today:
        return 'OVERDUE'
    if invoice.billing_period_end <= today + timedelta(days=DUE_SOON_WINDOW_DAYS):
        return 'DUE_SOON'
    return 'CURRENT'


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@strawberry.type
class Query:
    # --- Authenticated: current user ---------------------------------------
    @strawberry.field
    @login_required
    def me(self, info: Info) -> UserType:
        return info.context.request.user

    # --- ADMIN only --------------------------------------------------------
    @strawberry.field
    @require_roles(UserRole.ADMIN)
    def users(self, info: Info) -> List[UserType]:
        return User.objects.all()

    # --- ADMIN + FINANCE (financial data) ----------------------------------
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def invoices(self, info: Info) -> List[InvoiceType]:
        return Invoice.objects.all()

    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def payments(self, info: Info) -> List[PaymentType]:
        return Payment.objects.all()

    # A patient's invoice for a single billing month. `period` is "YYYY-MM";
    # `patient_id` is the patient's primary key. ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def invoice(
        self, info: Info, patient_id: strawberry.ID, period: str
    ) -> Optional[InvoiceType]:
        try:
            year, month = (int(part) for part in period.split('-'))
        except (ValueError, TypeError):
            raise GraphQLError('period must be in YYYY-MM format.')
        return (
            Invoice.objects.filter(
                admission__patient_id=patient_id,
                billing_period_start__year=year,
                billing_period_start__month=month,
            )
            .order_by('-billing_period_start')
            .first()
        )

    # All invoices for a patient, most recent period first. ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def invoice_list(self, info: Info, patient_id: strawberry.ID) -> List[InvoiceType]:
        return Invoice.objects.filter(
            admission__patient_id=patient_id
        ).order_by('-billing_period_start')

    # Active patients whose next billing cycle date falls within `within_days`
    # of today, sorted by due date. Defaults to the feeDueWarningDays system
    # setting. ADMIN + FINANCE only.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def fees_due_list(
        self, info: Info, within_days: Optional[int] = None
    ) -> List[FeeDueItem]:
        if within_days is None:
            within_days = settings.FEE_DUE_WARNING_DAYS
        if within_days < 0:
            raise GraphQLError('withinDays must be non-negative.')

        today = _today()
        items: List[FeeDueItem] = []
        active = Admission.objects.filter(
            status=AdmissionStatus.ACTIVE
        ).select_related('patient', 'bed__room')

        for admission in active:
            due_date = BillingService.next_billing_cycle_date(
                admission.admission_date, today
            )
            days_until_due = (due_date - today).days
            if days_until_due > within_days:
                continue

            # Projected amount: the recurring fee plus any charges already
            # logged for the upcoming billing period.
            following = BillingService.next_billing_cycle_date(
                admission.admission_date, due_date + timedelta(days=1)
            )
            charges = (
                AdditionalCharge.objects.filter(
                    admission=admission,
                    charge_date__gte=due_date,
                    charge_date__lte=following - timedelta(days=1),
                ).aggregate(total=Sum('amount'))['total']
                or Decimal('0')
            )

            items.append(
                FeeDueItem(
                    id=admission.patient.id,
                    patient_id=admission.patient.patient_id,
                    name=admission.patient.name,
                    room=admission.bed.room.name,
                    due_date=due_date,
                    amount_due=admission.monthly_fee + charges,
                    days_until_due=days_until_due,
                )
            )

        items.sort(key=lambda item: item.due_date)
        return items

    # --- ADMIN + NURSE (clinical data) -------------------------------------
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def vital_readings(self, info: Info) -> List[VitalReadingType]:
        return VitalReading.objects.all()

    # --- Any authenticated user (reference / operational data) -------------
    @strawberry.field
    @login_required
    def rooms(self, info: Info) -> List[RoomType]:
        return Room.objects.all()

    @strawberry.field
    @login_required
    def beds(self, info: Info, status: Optional[str] = None) -> List[BedType]:
        qs = Bed.objects.select_related('room').all()
        if status is not None:
            qs = qs.filter(status=status)
        return qs

    @strawberry.field
    @login_required
    def patients(self, info: Info) -> List[PatientType]:
        return Patient.objects.all()

    @strawberry.field
    @login_required
    def patient(self, info: Info, pk: strawberry.ID) -> Optional[PatientType]:
        return Patient.objects.filter(pk=pk).first()

    # Fuzzy patient search across name, patient_id, guardian name and phone.
    # Open to any authenticated role. Each result carries the patient's current
    # admission (date/room/bed) and a derived fee status.
    @strawberry.field
    @login_required
    def search_patients(self, info: Info, query: str) -> List[PatientSearchResult]:
        term = query.strip()
        if not term:
            return []

        patients = (
            Patient.objects.filter(
                Q(name__icontains=term)
                | Q(patient_id__icontains=term)
                | Q(guardian_name__icontains=term)
                | Q(guardian_phone__icontains=term)
            )
            .distinct()
            .order_by('name')
        )

        results: List[PatientSearchResult] = []
        for patient in patients:
            # Prefer the active admission; fall back to the most recent one.
            admission = (
                patient.admissions.filter(status=AdmissionStatus.ACTIVE)
                .select_related('bed__room')
                .order_by('-admission_date')
                .first()
                or patient.admissions.select_related('bed__room')
                .order_by('-admission_date')
                .first()
            )
            results.append(
                PatientSearchResult(
                    id=patient.id,
                    patient_id=patient.patient_id,
                    name=patient.name,
                    guardian_name=patient.guardian_name,
                    guardian_phone=patient.guardian_phone,
                    admission_date=admission.admission_date if admission else None,
                    room=admission.bed.room.name if admission else None,
                    bed=admission.bed.label if admission else None,
                    fee_status=_fee_status_for_patient(patient),
                )
            )
        return results

    @strawberry.field
    @login_required
    def admissions(self, info: Info) -> List[AdmissionType]:
        return Admission.objects.all()

    @strawberry.field
    @login_required
    def admission(self, info: Info, pk: strawberry.ID) -> Optional[AdmissionType]:
        return Admission.objects.filter(pk=pk).first()

    @strawberry.field
    @login_required
    def additional_charges(self, info: Info) -> List[AdditionalChargeType]:
        return AdditionalCharge.objects.all()

    @strawberry.field
    @login_required
    def vitals_thresholds(self, info: Info) -> List[VitalsThresholdType]:
        return VitalsThreshold.objects.all()


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

@strawberry.type
class Mutation:
    @strawberry.mutation
    def login(self, email: str, password: str) -> AuthTokens:
        user = auth.authenticate_user(email, password)
        if user is None:
            raise GraphQLError('Invalid email or password.')
        return AuthTokens(
            access_token=auth.create_access_token(user),
            refresh_token=auth.create_refresh_token(user),
        )

    @strawberry.mutation
    def refresh_token(self, refresh_token: str) -> AuthTokens:
        try:
            payload = auth.decode_token(refresh_token, expected_type='refresh')
        except auth.TokenError as exc:
            raise GraphQLError(str(exc))
        try:
            user = User.objects.get(pk=payload['user_id'], is_active=True)
        except User.DoesNotExist:
            raise GraphQLError('User no longer exists or is inactive.')
        # Rotate both tokens (stateless — old tokens remain valid until expiry).
        return AuthTokens(
            access_token=auth.create_access_token(user),
            refresh_token=auth.create_refresh_token(user),
        )

    # Example role-gated write: only ADMIN/FINANCE may record payments,
    # and recorded_by is stamped from the authenticated user.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def record_payment(
        self,
        info: Info,
        invoice_id: strawberry.ID,
        amount: Decimal,
        paid_on: date,
    ) -> PaymentType:
        try:
            invoice = Invoice.objects.get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise GraphQLError('Invoice not found.')
        return Payment.objects.create(
            invoice=invoice,
            amount=amount,
            paid_on=paid_on,
            recorded_by=info.context.request.user,
        )

    # Record a payment against an invoice and recompute its status.
    # FINANCE only.
    @strawberry.mutation
    @require_roles(UserRole.FINANCE)
    def log_payment(
        self,
        info: Info,
        invoice_id: strawberry.ID,
        amount: Decimal,
        paid_on: date,
    ) -> InvoiceType:
        if amount <= 0:
            raise GraphQLError('Payment amount must be positive.')
        with transaction.atomic():
            try:
                invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            except Invoice.DoesNotExist:
                raise GraphQLError('Invoice not found.')
            Payment.objects.create(
                invoice=invoice,
                amount=amount,
                paid_on=paid_on,
                recorded_by=info.context.request.user,
            )
            BillingService.recompute_status(invoice)
        return invoice

    # Record a refund against an invoice and recompute its status. FINANCE only.
    @strawberry.mutation
    @require_roles(UserRole.FINANCE)
    def log_refund(
        self, info: Info, invoice_id: strawberry.ID, amount: Decimal
    ) -> InvoiceType:
        if amount <= 0:
            raise GraphQLError('Refund amount must be positive.')
        with transaction.atomic():
            try:
                invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            except Invoice.DoesNotExist:
                raise GraphQLError('Invoice not found.')
            invoice.refund_amount = (invoice.refund_amount or Decimal('0')) + amount
            invoice.save(update_fields=['refund_amount'])
            BillingService.recompute_status(invoice)
        return invoice

    # Log an additional charge against an active admission. FINANCE only.
    @strawberry.mutation
    @require_roles(UserRole.FINANCE)
    def create_charge(
        self,
        info: Info,
        admission_id: strawberry.ID,
        category: ChargeCategoryEnum,
        amount: Decimal,
        charge_date: date,
        description: Optional[str] = "",
    ) -> AdditionalChargeType:
        if amount <= 0:
            raise GraphQLError('Charge amount must be positive.')
        try:
            admission = Admission.objects.get(pk=admission_id)
        except Admission.DoesNotExist:
            raise GraphQLError('Admission not found.')
        if admission.status != AdmissionStatus.ACTIVE:
            raise GraphQLError('Cannot add a charge to a discharged admission.')

        return AdditionalCharge.objects.create(
            admission=admission,
            category=category.value,
            amount=amount,
            charge_date=charge_date,
            description=description or '',
            recorded_by=info.context.request.user,
        )

    # Delete a charge, but only before its billing period has been invoiced.
    # FINANCE only.
    @strawberry.mutation
    @require_roles(UserRole.FINANCE)
    def delete_charge(self, info: Info, charge_id: strawberry.ID) -> bool:
        try:
            charge = AdditionalCharge.objects.select_related('admission').get(
                pk=charge_id
            )
        except AdditionalCharge.DoesNotExist:
            raise GraphQLError('Charge not found.')

        start, end = BillingService._period_for(
            charge.admission.admission_date, charge.charge_date
        )
        already_invoiced = Invoice.objects.filter(
            admission=charge.admission,
            billing_period_start=start,
            billing_period_end=end,
        ).exists()
        if already_invoiced:
            raise GraphQLError(
                'Cannot delete a charge that has already been invoiced.'
            )

        charge.delete()
        return True

    # Register a new patient and admit them to a bed in one atomic step.
    # ADMIN only. The patient_id is auto-generated by Patient.save(), and the
    # chosen bed is flipped to OCCUPIED. A row-level lock on the bed prevents
    # two concurrent admissions from racing into the same bed.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def create_admission(self, info: Info, input: CreateAdmissionInput) -> AdmissionType:
        if not input.name.strip():
            raise GraphQLError('Patient name is required.')
        if input.age < 0:
            raise GraphQLError('Age must be a positive number.')
        if input.monthly_fee < 0:
            raise GraphQLError('Monthly fee cannot be negative.')

        with transaction.atomic():
            try:
                bed = Bed.objects.select_for_update().get(pk=input.bed_id)
            except Bed.DoesNotExist:
                raise GraphQLError('Bed not found.')

            if bed.status == BedStatus.OCCUPIED:
                raise GraphQLError('Bed is already occupied.')

            patient = Patient.objects.create(
                name=input.name.strip(),
                age=input.age,
                diagnosis=input.diagnosis,
                guardian_name=input.guardian_name or '',
                guardian_phone=input.guardian_phone or '',
                admitting_doctor=input.admitting_doctor,
            )
            admission = Admission.objects.create(
                patient=patient,
                bed=bed,
                admission_date=input.admission_date,
                monthly_fee=input.monthly_fee,
                status=AdmissionStatus.ACTIVE,
            )
            bed.status = BedStatus.OCCUPIED
            bed.save(update_fields=['status'])

        return admission

    # Discharge a patient: mark the admission DISCHARGED and free the bed.
    # ADMIN and FINANCE may discharge (NURSE may not). Only FINANCE may attach
    # a refund_amount. Returns a warning flag when the patient still has
    # outstanding (unpaid/partial) invoices.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def discharge_patient(
        self,
        info: Info,
        admission_id: strawberry.ID,
        refund_amount: Optional[Decimal] = None,
        discharge_type: Optional[str] = None,
        discharge_notes: Optional[str] = None,
    ) -> DischargeResult:
        user = info.context.request.user

        # A refund may only be recorded by Finance.
        if refund_amount is not None:
            if user.role != UserRole.FINANCE:
                raise GraphQLError('Only Finance can record a refund on discharge.')
            if refund_amount < 0:
                raise GraphQLError('Refund amount cannot be negative.')

        with transaction.atomic():
            try:
                admission = (
                    Admission.objects.select_for_update()
                    .select_related('bed')
                    .get(pk=admission_id)
                )
            except Admission.DoesNotExist:
                raise GraphQLError('Admission not found.')

            if admission.status == AdmissionStatus.DISCHARGED:
                raise GraphQLError('Patient is already discharged.')

            outstanding_count = admission.invoices.filter(
                status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]
            ).count()

            admission.status = AdmissionStatus.DISCHARGED
            admission.discharge_date = date.today()
            if discharge_type:
                admission.discharge_type = discharge_type
            if discharge_notes:
                admission.discharge_notes = discharge_notes
            if refund_amount is not None:
                admission.refund_amount = refund_amount
            admission.save()

            # Free the bed.
            bed = admission.bed
            bed.status = BedStatus.VACANT
            bed.save(update_fields=['status'])

        return DischargeResult(
            admission=admission,
            has_outstanding_dues=outstanding_count > 0,
            outstanding_invoice_count=outstanding_count,
            refund_amount=admission.refund_amount,
        )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[DjangoOptimizerExtension],
)
