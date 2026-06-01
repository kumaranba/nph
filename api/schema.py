from datetime import date
from decimal import Decimal
from typing import List, Optional

import strawberry
from django.db import transaction
from graphql import GraphQLError
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

from . import auth
from .models import (
    AdditionalCharge, Admission, AdmissionStatus, Bed, BedStatus, Invoice,
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


# ---------------------------------------------------------------------------
# Mutation inputs
# ---------------------------------------------------------------------------

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


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[DjangoOptimizerExtension],
)
