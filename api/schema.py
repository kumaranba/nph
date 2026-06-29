from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

import strawberry
from django.db.models import Q
from graphql import GraphQLError
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

from . import auth
from .models import (
    AdditionalCharge, Admission, AdmissionStatus, Bed, Invoice, InvoiceStatus,
    Patient, Payment, Room, User, UserRole, VitalReading, VitalsThreshold,
)
from .permissions import login_required, require_roles
from .types import (
    AdditionalChargeType, AdmissionType, BedType, InvoiceType, PatientType,
    PaymentType, RoomType, UserType, VitalReadingType, VitalsThresholdType,
)


# ---------------------------------------------------------------------------
# Auth payload
# ---------------------------------------------------------------------------

@strawberry.type
class AuthTokens:
    access_token: str
    refresh_token: str


# Number of days before an invoice's period end that we flag it "due soon".
DUE_SOON_WINDOW_DAYS = 7


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
