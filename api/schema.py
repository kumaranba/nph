from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional

import strawberry
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from graphql import GraphQLError
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

from . import auth, dashboard, vitals
from .billing import BillingService
from .fees import FeeError, FeeService
from .models import (
    AdditionalCharge, Admission, AdmissionStatus, Bed, BedStatus, Fee, Gender,
    Invoice, InvoiceStatus, Patient, Payment, PaymentAccount, PaymentReceipt,
    Room, SystemSetting, Tag, TagCategory, User, UserRole, VitalReading,
    VitalsThreshold,
)
from .permissions import login_required, require_roles
from .types import (
    AdditionalChargeType, AdmissionType, BedType, FeeType, InvoiceType,
    PatientType, PaymentAccountType, PaymentReceiptType, PaymentType, RoomType,
    TagType, UserType, VitalReadingType, VitalsThresholdType,
)


# ---------------------------------------------------------------------------
# Auth payload
# ---------------------------------------------------------------------------

@strawberry.enum
class UserRoleEnum(Enum):
    """GraphQL enum for User.role (mirrors models.UserRole)."""
    ADMIN = 'ADMIN'
    FINANCE = 'FINANCE'
    NURSE = 'NURSE'


@strawberry.enum
class ChargeCategoryEnum(Enum):
    """GraphQL enum for AdditionalCharge.category (mirrors models.ChargeCategory)."""
    DRUGS = 'DRUGS'
    SNACKS = 'SNACKS'
    PERSONAL_CARE = 'PERSONAL_CARE'
    SPECIALIST = 'SPECIALIST'
    OTHER = 'OTHER'


@strawberry.enum
class GenderEnum(Enum):
    """GraphQL enum for Patient.gender (mirrors models.Gender)."""
    MALE = 'MALE'
    FEMALE = 'FEMALE'
    OTHER = 'OTHER'


@strawberry.enum
class TagCategoryEnum(Enum):
    """GraphQL enum for Tag.category (mirrors models.TagCategory)."""
    BEHAVIOUR = 'BEHAVIOUR'
    ILLNESS = 'ILLNESS'
    OTHER = 'OTHER'


@strawberry.enum
class TagMatchEnum(Enum):
    """How a multi-tag patient search combines the requested tags."""
    ANY = 'ANY'   # patient carries at least one of the tags
    ALL = 'ALL'   # patient carries every tag


@strawberry.enum
class VitalSessionEnum(Enum):
    """GraphQL enum for VitalReading.session (mirrors models.VitalSession)."""
    AM = 'AM'
    PM = 'PM'


@strawberry.enum
class VitalTypeEnum(Enum):
    """GraphQL enum for VitalsThreshold.vital_type (mirrors models.VitalType)."""
    BP_SYSTOLIC = 'BP_SYSTOLIC'
    BP_DIASTOLIC = 'BP_DIASTOLIC'
    PULSE = 'PULSE'
    TEMPERATURE = 'TEMPERATURE'
    SPO2 = 'SPO2'
    WEIGHT = 'WEIGHT'


@strawberry.input
class VitalsThresholdInput:
    """A single threshold update. A null bound means that side is unbounded."""
    vital_type: VitalTypeEnum
    below_threshold: Optional[Decimal] = None
    above_threshold: Optional[Decimal] = None


@strawberry.type
class SystemSettingsType:
    """Editable, runtime-configurable app settings."""
    fee_due_warning_days: int
    vitals_thresholds: List[VitalsThresholdType]


def _system_settings() -> SystemSettingsType:
    return SystemSettingsType(
        fee_due_warning_days=SystemSetting.load().fee_due_warning_days,
        vitals_thresholds=list(VitalsThreshold.objects.order_by('vital_type')),
    )


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
    diagnosis: str
    admitting_doctor: str
    # Admission details
    bed_id: Optional[strawberry.ID] = None
    admission_date: date
    monthly_fee: Decimal
    # Optional patient details
    age: Optional[int] = None
    guardian_name: Optional[str] = ""
    guardian_phone: Optional[str] = ""
    gender: Optional[GenderEnum] = None


@strawberry.input
class UpdatePatientInput:
    """Editable patient profile fields. Every field is optional: only the ones
    provided are changed (UNSET means "leave as-is"). ``age`` and ``gender`` may
    be explicitly cleared by sending null.
    """
    name: Optional[str] = strawberry.UNSET
    age: Optional[int] = strawberry.UNSET
    gender: Optional[GenderEnum] = strawberry.UNSET
    diagnosis: Optional[str] = strawberry.UNSET
    admitting_doctor: Optional[str] = strawberry.UNSET
    guardian_name: Optional[str] = strawberry.UNSET
    guardian_phone: Optional[str] = strawberry.UNSET
    place: Optional[str] = strawberry.UNSET


# Number of days before an invoice's period end that we flag it "due soon".
DUE_SOON_WINDOW_DAYS = 7


def _today() -> date:
    """Indirection so tests can pin "today" deterministically."""
    return date.today()


@strawberry.type
class PendingDueItem:
    """An active patient who currently owes money, for the pending-dues list
    and the fees-due PDF. Includes past dues (overdue months + carried opening
    balance), unlike FeeDueItem which is forward-looking."""
    id: strawberry.ID          # patient primary key (for navigation)
    patient_id: str            # NPH-YYYY-NNNN code
    name: str
    gender: str
    room: Optional[str]
    admission_date: date       # DOA
    current_fees: Decimal      # current cycle's charge (monthly fee + charges)
    total_pending_dues: Decimal
    contact: str
    place: str


@strawberry.type
class FeeDueItem:
    """A patient with an upcoming billing cycle date, for the fees-due list."""
    id: strawberry.ID          # patient primary key (for navigation)
    patient_id: str            # NPH-YYYY-NNNN code
    name: str
    room: Optional[str]
    due_date: date
    amount_due: Decimal        # the upcoming cycle: monthly fee + period charges
    # Unpaid carried-forward opening balance, shown alongside (not folded into)
    # amount_due so the same money is never counted twice. total_due_now is the
    # full ask: amount_due + opening_balance.
    opening_balance: Decimal
    total_due_now: Decimal
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
    tags: List[str]


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


def _patient_search_result(patient) -> PatientSearchResult:
    """Build a PatientSearchResult from a patient, resolving their current
    (or most recent) admission and derived fee status."""
    admission = (
        patient.admissions.filter(status=AdmissionStatus.ACTIVE)
        .select_related('bed__room')
        .order_by('-admission_date')
        .first()
        or patient.admissions.select_related('bed__room')
        .order_by('-admission_date')
        .first()
    )
    return PatientSearchResult(
        id=patient.id,
        patient_id=patient.patient_id,
        name=patient.name,
        guardian_name=patient.guardian_name,
        guardian_phone=patient.guardian_phone,
        admission_date=admission.admission_date if admission else None,
        room=admission.bed.room.name if admission and admission.bed else None,
        bed=admission.bed.label if admission and admission.bed else None,
        fee_status=_fee_status_for_patient(patient),
        tags=list(patient.tags.order_by('name').values_list('label', flat=True)),
    )


def build_pending_dues(as_of: date = None) -> List['PendingDueItem']:
    """Active admissions that currently owe money, highest dues first.

    Shared by the ``pendingDuesList`` query and the fees-due PDF. Includes past
    dues (overdue months + carried opening balance), not just the upcoming
    cycle. Patients with zero outstanding are excluded.
    """
    as_of = as_of or _today()
    items: List[PendingDueItem] = []
    active = (
        Admission.objects.filter(status=AdmissionStatus.ACTIVE)
        .select_related('patient', 'bed__room')
    )
    for admission in active:
        pending = BillingService.total_pending_dues(admission)
        if pending <= 0:
            continue
        patient = admission.patient
        items.append(
            PendingDueItem(
                id=patient.id,
                patient_id=patient.patient_id,
                name=patient.name,
                gender=patient.gender or '',
                room=admission.bed.room.name if admission.bed else None,
                admission_date=admission.admission_date,
                current_fees=BillingService.current_cycle_charge(admission, as_of),
                total_pending_dues=pending,
                contact=patient.guardian_phone or '',
                place=patient.place or '',
            )
        )
    items.sort(key=lambda i: i.total_pending_dues, reverse=True)
    return items


# ---------------------------------------------------------------------------
# Patient account statement
# ---------------------------------------------------------------------------

@strawberry.type
class StatementLine:
    """One ledger entry: a billed invoice (debit) or a payment received
    (credit), with the running account balance after it."""
    date: date
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


@strawberry.type
class AccountStatement:
    """A patient's account ledger over a date range. Balance is cash-based:
    invoices billed (debits) minus payments received (credits). A negative
    balance means the account is in advance credit."""
    patient_id: strawberry.ID
    patient_name: str
    patient_code: str
    date_from: Optional[date]
    date_to: Optional[date]
    opening_balance: Decimal
    closing_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    lines: List[StatementLine]


def build_account_statement(
    patient_id, date_from: date = None, date_to: date = None
) -> AccountStatement:
    """Build a patient's account statement across all their admissions.

    Debits are invoices (by billing period start; total_due already includes
    that period's additional charges). Credits are payments received (by
    paid_on). Shared by the ``accountStatement`` query and the statement PDF.
    """
    patient = Patient.objects.get(pk=patient_id)
    invoices = Invoice.objects.filter(admission__patient=patient)
    receipts = PaymentReceipt.objects.filter(admission__patient=patient)

    # Opening balance = everything billed less received strictly before the
    # range start.
    opening = Decimal('0')
    if date_from is not None:
        opening += sum(
            (i.total_due for i in invoices.filter(billing_period_start__lt=date_from)),
            Decimal('0'),
        )
        opening -= sum(
            (r.amount for r in receipts.filter(paid_on__lt=date_from)),
            Decimal('0'),
        )

    inv_q = invoices
    rcpt_q = receipts
    if date_from is not None:
        inv_q = inv_q.filter(billing_period_start__gte=date_from)
        rcpt_q = rcpt_q.filter(paid_on__gte=date_from)
    if date_to is not None:
        inv_q = inv_q.filter(billing_period_start__lte=date_to)
        rcpt_q = rcpt_q.filter(paid_on__lte=date_to)

    # (date, sort_rank, description, debit, credit). Invoices (rank 0) sort
    # before payments (rank 1) on the same day.
    events = []
    for inv in inv_q:
        desc = ('Opening balance' if inv.is_opening_balance
                else f"Fee — {inv.billing_period_start.strftime('%b %Y')}")
        events.append((inv.billing_period_start, 0, desc, inv.total_due, Decimal('0')))
    for r in rcpt_q:
        acct = f" ({r.account.name})" if r.account else ''
        events.append((r.paid_on, 1, f"Payment{acct}", Decimal('0'), r.amount))
    events.sort(key=lambda e: (e[0], e[1]))

    balance = opening
    lines: List[StatementLine] = []
    total_debits = Decimal('0')
    total_credits = Decimal('0')
    for d, _rank, desc, debit, credit in events:
        balance += debit - credit
        total_debits += debit
        total_credits += credit
        lines.append(StatementLine(
            date=d, description=desc, debit=debit, credit=credit, balance=balance,
        ))

    return AccountStatement(
        patient_id=patient.id,
        patient_name=patient.name,
        patient_code=patient.patient_id,
        date_from=date_from,
        date_to=date_to,
        opening_balance=opening,
        closing_balance=balance,
        total_debits=total_debits,
        total_credits=total_credits,
        lines=lines,
    )


def _resolve_active_account(account_id):
    """Look up an active PaymentAccount by id, or None if id is None.
    Raises GraphQLError if the id is given but not an active account."""
    if account_id is None:
        return None
    try:
        return PaymentAccount.objects.get(pk=account_id, is_active=True)
    except PaymentAccount.DoesNotExist:
        raise GraphQLError('Payment account not found.')


# ---------------------------------------------------------------------------
# Dashboard result types
# ---------------------------------------------------------------------------

@strawberry.type
class DashboardStats:
    beds_occupied: int
    beds_total: int
    outstanding_total: Decimal
    outstanding_invoice_count: int
    overdue_count: int
    fees_due_total: Decimal
    fees_due_count: int
    fees_due_today: int
    flagged_vitals_count: int
    flagged_patient_count: int
    critical_count: int


@strawberry.type
class MonthlyTotal:
    month: str
    total: Decimal


@strawberry.type
class FlaggedVitalItem:
    id: strawberry.ID
    patient_name: str
    room: str
    vital: str
    value: float
    direction: str          # "high" | "low"
    severity: str           # "critical" | "warning"
    recorded_at: datetime


@strawberry.type
class ActivityItem:
    id: strawberry.ID
    kind: str               # payment | admission | charge | vitals
    message: str
    actor: str
    created_at: str


@strawberry.type
class PaymentAllocation:
    """One invoice the payment was applied to."""
    invoice_id: strawberry.ID
    period: str             # "YYYY-MM"
    amount: Decimal


@strawberry.type
class RecordPaymentResult:
    """Outcome of a patient payment.

    ``allocations`` are the invoices cleared now; any surplus becomes advance
    ``credit_added`` and is reflected in the admission's ``credit_balance``,
    to be drawn down automatically as future monthly invoices come due.
    """
    patient_id: strawberry.ID
    receipt_id: strawberry.ID
    total_recorded: Decimal
    fees_amount: Decimal
    charges_amount: Decimal
    account: Optional[str]
    invoices_paid: int
    credit_added: Decimal
    credit_balance: Decimal
    allocations: List[PaymentAllocation]


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

    # Editable app settings: fee-due warning window and vitals thresholds.
    # ADMIN only.
    @strawberry.field
    @require_roles(UserRole.ADMIN)
    def system_settings(self, info: Info) -> SystemSettingsType:
        return _system_settings()

    # --- ADMIN + FINANCE (financial data) ----------------------------------
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def invoices(self, info: Info) -> List[InvoiceType]:
        return Invoice.objects.all()

    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def payments(self, info: Info) -> List[PaymentType]:
        return Payment.objects.all()

    # Active payment accounts (Nila / Vaigari / Bank AC …) for the record-
    # payment picker. ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def payment_accounts(self, info: Info) -> List[PaymentAccountType]:
        return PaymentAccount.objects.filter(is_active=True).order_by('name')

    # Payments received in a date range (each a receipt / payment event),
    # newest first. Bounds are inclusive; omit either for an open end.
    # ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def payment_receipts(
        self,
        info: Info,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[PaymentReceiptType]:
        qs = PaymentReceipt.objects.select_related(
            'admission__patient', 'account', 'recorded_by'
        )
        if date_from is not None:
            qs = qs.filter(paid_on__gte=date_from)
        if date_to is not None:
            qs = qs.filter(paid_on__lte=date_to)
        return qs.order_by('-paid_on', '-id')

    # A patient's account statement (invoices billed vs payments received) over
    # an optional date range, with a running balance. ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def account_statement(
        self,
        info: Info,
        patient_id: strawberry.ID,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> AccountStatement:
        try:
            return build_account_statement(patient_id, date_from, date_to)
        except Patient.DoesNotExist:
            raise GraphQLError('Patient not found.')

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

    # A patient's full fee history across all admissions, newest first.
    # ADMIN + FINANCE may view (ADMIN is view-only; only FINANCE may change).
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def fee_history(self, info: Info, patient_id: strawberry.ID) -> List[FeeType]:
        return list(FeeService.get_fee_history(patient_id))

    # Active patients whose next billing cycle date falls within `within_days`
    # of today, sorted by due date. Defaults to the feeDueWarningDays system
    # setting. ADMIN + FINANCE only.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def fees_due_list(
        self, info: Info, within_days: Optional[int] = None
    ) -> List[FeeDueItem]:
        if within_days is None:
            within_days = SystemSetting.load().fee_due_warning_days
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

            amount_due = admission.monthly_fee + charges
            opening_inv = admission.invoices.filter(is_opening_balance=True).first()
            opening_balance = (
                BillingService.balance_due(opening_inv)
                if opening_inv is not None else Decimal('0')
            )

            items.append(
                FeeDueItem(
                    id=admission.patient.id,
                    patient_id=admission.patient.patient_id,
                    name=admission.patient.name,
                    room=admission.bed.room.name if admission.bed else None,
                    due_date=due_date,
                    amount_due=amount_due,
                    opening_balance=opening_balance,
                    total_due_now=amount_due + opening_balance,
                    days_until_due=days_until_due,
                )
            )

        items.sort(key=lambda item: item.due_date)
        return items

    # Active patients who currently owe money (past dues included), highest
    # outstanding first. Backs the pending-dues view and the fees-due PDF.
    # ADMIN + FINANCE only.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def pending_dues_list(self, info: Info) -> List[PendingDueItem]:
        return build_pending_dues()

    # --- ADMIN + NURSE (clinical data) -------------------------------------
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def vital_readings(self, info: Info) -> List[VitalReadingType]:
        return VitalReading.objects.all()

    # A patient's vitals history, sorted by recorded_at (oldest first).
    # Optionally filtered by date range and by vital types (readings that
    # recorded at least one of the requested vitals). ADMIN + NURSE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def vital_history(
        self,
        info: Info,
        patient_id: strawberry.ID,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        types: Optional[List[str]] = None,
    ) -> List[VitalReadingType]:
        qs = VitalReading.objects.filter(admission__patient_id=patient_id)

        if date_from is not None:
            qs = qs.filter(
                recorded_at__gte=timezone.make_aware(
                    datetime.combine(date_from, time.min)
                )
            )
        if date_to is not None:
            # Inclusive of the whole `date_to` day.
            qs = qs.filter(
                recorded_at__lt=timezone.make_aware(
                    datetime.combine(date_to + timedelta(days=1), time.min)
                )
            )

        if types:
            type_q = Q()
            matched = False
            for vital_type in types:
                field = vitals.VITAL_FIELD_BY_TYPE.get(vital_type)
                if field:
                    type_q |= Q(**{f'{field}__isnull': False})
                    matched = True
            if matched:
                qs = qs.filter(type_q)

        return qs.order_by('recorded_at')

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

        return [_patient_search_result(patient) for patient in patients]

    # Find patients by tag. `tags` are matched case-insensitively by label or
    # canonical name; `match` is ANY (default) or ALL. Any authenticated role.
    @strawberry.field
    @login_required
    def patients_by_tags(
        self,
        info: Info,
        tags: List[str],
        match: TagMatchEnum = TagMatchEnum.ANY,
    ) -> List[PatientSearchResult]:
        names = [t.strip().lower() for t in tags if t and t.strip()]
        if not names:
            return []

        if match == TagMatchEnum.ALL:
            patients = Patient.objects.all()
            for name in names:
                patients = patients.filter(tags__name=name)
            patients = patients.distinct()
        else:
            patients = Patient.objects.filter(tags__name__in=names).distinct()

        patients = patients.order_by('name')
        return [_patient_search_result(patient) for patient in patients]

    # Tag typeahead. Empty query returns the most-used tags; otherwise a
    # case-insensitive substring match, ranked by usage then name. Optionally
    # filtered by category. Any authenticated role.
    @strawberry.field
    @login_required
    def tag_suggestions(
        self,
        info: Info,
        query: Optional[str] = None,
        category: Optional[TagCategoryEnum] = None,
        limit: int = 10,
    ) -> List[TagType]:
        qs = Tag.objects.all()
        if category is not None:
            qs = qs.filter(category=category.value)
        term = (query or '').strip()
        if term:
            qs = qs.filter(Q(name__icontains=term.lower()) | Q(label__icontains=term))
        qs = qs.annotate(_use_count=Count('patients')).order_by('-_use_count', 'name')
        return list(qs[: max(1, min(limit, 50))])

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

    # --- Dashboard ---------------------------------------------------------
    # Aggregate overview counts. Any authenticated staff member.
    @strawberry.field
    @login_required
    def dashboard_stats(self, info: Info) -> DashboardStats:
        return DashboardStats(**dashboard.compute_stats())

    # Monthly payment totals for the trend chart. ADMIN + FINANCE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def payments_trend(self, info: Info, months: int = 6) -> List[MonthlyTotal]:
        months = max(1, min(months, 24))
        return [MonthlyTotal(**b) for b in dashboard.payments_trend(months)]

    # Out-of-range vitals feed for active patients. ADMIN + NURSE.
    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def flagged_vitals(
        self, info: Info, limit: Optional[int] = None
    ) -> List[FlaggedVitalItem]:
        return [FlaggedVitalItem(**i) for i in dashboard.flagged_vital_items(limit)]

    # Most recent admissions. Any authenticated staff member.
    @strawberry.field
    @login_required
    def recent_admissions(
        self, info: Info, limit: int = 5
    ) -> List[AdmissionType]:
        return (
            Admission.objects.select_related('patient', 'bed__room')
            .order_by('-admission_date', '-id')[: max(1, min(limit, 50))]
        )

    # Wards (rooms) with their beds. Any authenticated staff member.
    @strawberry.field
    @login_required
    def wards(self, info: Info) -> List[RoomType]:
        return Room.objects.prefetch_related('beds').order_by('name')

    # Synthesized recent-activity feed. Any authenticated staff member.
    @strawberry.field
    @login_required
    def activity_log(self, info: Info, limit: int = 10) -> List[ActivityItem]:
        return [
            ActivityItem(**i)
            for i in dashboard.activity_items(max(1, min(limit, 50)))
        ]


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
        # Grouped under a receipt so it appears in payments history / statement.
        receipt = PaymentReceipt.objects.create(
            admission=invoice.admission,
            paid_on=paid_on,
            amount=amount,
            fees_amount=amount,
            charges_amount=Decimal('0'),
            recorded_by=info.context.request.user,
        )
        return Payment.objects.create(
            invoice=invoice,
            amount=amount,
            paid_on=paid_on,
            recorded_by=info.context.request.user,
            receipt=receipt,
        )

    # Record a payment for a PATIENT (not a single invoice). Clears their
    # outstanding invoices oldest-first, then applies any surplus as an advance
    # against upcoming monthly invoices. ADMIN + FINANCE.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def record_patient_payment(
        self,
        info: Info,
        patient_id: strawberry.ID,
        paid_on: date,
        fees_amount: Decimal = Decimal('0'),
        charges_amount: Decimal = Decimal('0'),
        account_id: Optional[strawberry.ID] = None,
    ) -> RecordPaymentResult:
        if fees_amount < 0 or charges_amount < 0:
            raise GraphQLError('Amounts cannot be negative.')
        if fees_amount + charges_amount <= 0:
            raise GraphQLError('Payment total must be positive.')

        account = _resolve_active_account(account_id)

        admission = (
            Admission.objects.filter(
                patient_id=patient_id, status=AdmissionStatus.ACTIVE
            )
            .order_by('-admission_date')
            .first()
            or Admission.objects.filter(patient_id=patient_id)
            .order_by('-admission_date')
            .first()
        )
        if admission is None:
            raise GraphQLError('No admission found for this patient.')

        receipt, allocations, credit_added = (
            BillingService.record_payment_for_admission(
                admission, fees_amount, charges_amount, paid_on,
                info.context.request.user, account=account,
            )
        )
        admission.refresh_from_db()
        return RecordPaymentResult(
            patient_id=admission.patient_id,
            receipt_id=receipt.id,
            total_recorded=receipt.amount,
            fees_amount=receipt.fees_amount,
            charges_amount=receipt.charges_amount,
            account=account.name if account else None,
            invoices_paid=len(allocations),
            credit_added=credit_added,
            credit_balance=admission.credit_balance,
            allocations=[
                PaymentAllocation(
                    invoice_id=inv.id,
                    period=inv.billing_period_start.strftime('%Y-%m'),
                    amount=amt,
                )
                for inv, amt in allocations
            ],
        )

    # Change an admission's fee. FINANCE only. effective_from defaults to the
    # next not-yet-invoiced billing cycle; an explicit different date needs
    # override=True. Deactivates the current active fee and creates a new one.
    @strawberry.mutation
    @require_roles(UserRole.FINANCE)
    def change_fee(
        self,
        info: Info,
        admission_id: strawberry.ID,
        amount: Decimal,
        reason: str,
        effective_from: Optional[date] = None,
        override: bool = False,
    ) -> FeeType:
        try:
            return FeeService.change_fee(
                admission_id=admission_id,
                amount=amount,
                reason=reason,
                user=info.context.request.user,
                effective_from=effective_from,
                override=override,
            )
        except Admission.DoesNotExist:
            raise GraphQLError('Admission not found.')
        except FeeError as exc:
            raise GraphQLError(str(exc))

    # Record a payment against an invoice and recompute its status.
    # ADMIN + FINANCE.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def log_payment(
        self,
        info: Info,
        invoice_id: strawberry.ID,
        amount: Decimal,
        paid_on: date,
        account_id: Optional[strawberry.ID] = None,
    ) -> InvoiceType:
        if amount <= 0:
            raise GraphQLError('Payment amount must be positive.')
        account = _resolve_active_account(account_id)
        with transaction.atomic():
            try:
                invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            except Invoice.DoesNotExist:
                raise GraphQLError('Invoice not found.')
            # Group this payment under a receipt so it appears in payments
            # history and counts as a credit on the account statement. The whole
            # amount is recorded against fees (this flow has no fees/charges
            # split); the split is informational only.
            receipt = PaymentReceipt.objects.create(
                admission=invoice.admission,
                paid_on=paid_on,
                amount=amount,
                fees_amount=amount,
                charges_amount=Decimal('0'),
                account=account,
                recorded_by=info.context.request.user,
            )
            Payment.objects.create(
                invoice=invoice,
                amount=amount,
                paid_on=paid_on,
                recorded_by=info.context.request.user,
                receipt=receipt,
            )
            BillingService.recompute_status(invoice)
        return invoice

    # Record a refund against an invoice and recompute its status.
    # ADMIN + FINANCE.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
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

    # Record a vitals reading. The server stamps recorded_at and evaluates
    # has_flag against the VitalsThreshold table. ADMIN + NURSE.
    # Multiple readings per session/day are allowed (not blocked).
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def create_vital_reading(
        self,
        info: Info,
        admission_id: strawberry.ID,
        session: VitalSessionEnum,
        bp_systolic: int,
        bp_diastolic: int,
        pulse: int,
        temperature: Decimal,
        spo2: int,
        weight: Optional[Decimal] = None,
        notes: Optional[str] = "",
    ) -> VitalReadingType:
        try:
            admission = Admission.objects.get(pk=admission_id)
        except Admission.DoesNotExist:
            raise GraphQLError('Admission not found.')

        reading = VitalReading(
            admission=admission,
            session=session.value,
            recorded_at=timezone.now(),
            recorded_by=info.context.request.user,
            bp_systolic=bp_systolic,
            bp_diastolic=bp_diastolic,
            pulse=pulse,
            temperature=temperature,
            spo2=spo2,
            weight=weight,
            notes=notes or '',
        )
        # Flag before saving, comparing each value against its threshold.
        reading.has_flag = vitals.has_flag(reading)
        reading.save()
        return reading

    # Register a new patient and admit them to a bed in one atomic step.
    # ADMIN only. The patient_id is auto-generated by Patient.save(), and the
    # chosen bed is flipped to OCCUPIED. A row-level lock on the bed prevents
    # two concurrent admissions from racing into the same bed.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def create_admission(self, info: Info, input: CreateAdmissionInput) -> AdmissionType:
        if not input.name.strip():
            raise GraphQLError('Patient name is required.')
        if input.age is not None and input.age < 0:
            raise GraphQLError('Age must be a positive number.')
        if input.monthly_fee < 0:
            raise GraphQLError('Monthly fee cannot be negative.')

        with transaction.atomic():
            bed = None
            if input.bed_id is not None:
                try:
                    bed = Bed.objects.select_for_update().get(pk=input.bed_id)
                except Bed.DoesNotExist:
                    raise GraphQLError('Bed not found.')
                if bed.status == BedStatus.OCCUPIED:
                    raise GraphQLError('Bed is already occupied.')

            patient = Patient.objects.create(
                name=input.name.strip(),
                age=input.age,
                gender=input.gender.value if input.gender else '',
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
            # Establish the admission's initial active fee.
            Fee.objects.create(
                admission=admission,
                amount=input.monthly_fee,
                effective_from=input.admission_date,
                is_active=True,
                reason='Initial fee',
                created_by=info.context.request.user,
            )
            if bed is not None:
                bed.status = BedStatus.OCCUPIED
                bed.save(update_fields=['status'])

            # Bill every period already due (admission may be back-dated), so an
            # unpaid new admission surfaces immediately in fees-due / pending
            # dues rather than only after the next daily billing run.
            BillingService.generate_all_due_for_admission(admission.id)

        return admission

    # Edit a patient's profile fields. ADMIN only. Only the fields provided are
    # changed; age/gender may be cleared by sending null.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def update_patient(
        self, info: Info, patient_id: strawberry.ID, input: UpdatePatientInput
    ) -> PatientType:
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            raise GraphQLError('Patient not found.')

        UNSET = strawberry.UNSET
        update_fields = []

        if input.name is not UNSET:
            if not (input.name or '').strip():
                raise GraphQLError('Patient name cannot be empty.')
            patient.name = input.name.strip()
            update_fields.append('name')
        if input.age is not UNSET:
            if input.age is not None and input.age < 0:
                raise GraphQLError('Age must be a positive number.')
            patient.age = input.age
            update_fields.append('age')
        if input.gender is not UNSET:
            patient.gender = input.gender.value if input.gender else ''
            update_fields.append('gender')
        if input.diagnosis is not UNSET:
            patient.diagnosis = input.diagnosis or ''
            update_fields.append('diagnosis')
        if input.admitting_doctor is not UNSET:
            patient.admitting_doctor = input.admitting_doctor or ''
            update_fields.append('admitting_doctor')
        if input.guardian_name is not UNSET:
            patient.guardian_name = input.guardian_name or ''
            update_fields.append('guardian_name')
        if input.guardian_phone is not UNSET:
            patient.guardian_phone = input.guardian_phone or ''
            update_fields.append('guardian_phone')
        if input.place is not UNSET:
            patient.place = input.place or ''
            update_fields.append('place')

        if update_fields:
            patient.save(update_fields=update_fields)
        return patient

    # Attach one or more tags to a patient, creating any that don't yet exist
    # (matched case-insensitively). `category` is applied only to newly-created
    # tags. ADMIN + NURSE. Returns the updated patient.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def add_patient_tags(
        self,
        info: Info,
        patient_id: strawberry.ID,
        tags: List[str],
        category: Optional[TagCategoryEnum] = None,
    ) -> PatientType:
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            raise GraphQLError('Patient not found.')

        cat = category.value if category else TagCategory.OTHER
        with transaction.atomic():
            for raw in tags:
                tag, _ = Tag.get_or_create_normalized(raw, category=cat)
                if tag is not None:
                    patient.tags.add(tag)
        return patient

    # Remove a single tag from a patient (matched case-insensitively by label
    # or canonical name). The Tag row itself is preserved. ADMIN + NURSE.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN, UserRole.NURSE)
    def remove_patient_tag(
        self, info: Info, patient_id: strawberry.ID, tag: str
    ) -> PatientType:
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            raise GraphQLError('Patient not found.')
        name = (tag or '').strip().lower()
        existing = patient.tags.filter(name=name).first()
        if existing is not None:
            patient.tags.remove(existing)
        return patient

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

            # A discharged admission holds no active fee.
            FeeService.deactivate_fee_on_discharge(admission.id)

            # Free the bed if one was assigned.
            if admission.bed is not None:
                admission.bed.status = BedStatus.VACANT
                admission.bed.save(update_fields=['status'])

        return DischargeResult(
            admission=admission,
            has_outstanding_dues=outstanding_count > 0,
            outstanding_invoice_count=outstanding_count,
            refund_amount=admission.refund_amount,
        )

    # Update editable app settings. Any field left null is unchanged; only the
    # thresholds included in `thresholds` are upserted. ADMIN only.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def update_settings(
        self,
        info: Info,
        fee_due_warning_days: Optional[int] = None,
        thresholds: Optional[List[VitalsThresholdInput]] = None,
    ) -> SystemSettingsType:
        with transaction.atomic():
            if fee_due_warning_days is not None:
                if fee_due_warning_days < 0:
                    raise GraphQLError('feeDueWarningDays must be non-negative.')
                setting = SystemSetting.load()
                setting.fee_due_warning_days = fee_due_warning_days
                setting.save()

            for threshold in thresholds or []:
                VitalsThreshold.objects.update_or_create(
                    vital_type=threshold.vital_type.value,
                    defaults={
                        'below_threshold': threshold.below_threshold,
                        'above_threshold': threshold.above_threshold,
                    },
                )

        return _system_settings()

    # Create a staff user with a role. ADMIN only.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def create_user(
        self, info: Info, email: str, password: str, role: UserRoleEnum
    ) -> UserType:
        email = email.strip().lower()
        if not email:
            raise GraphQLError('Email is required.')
        if len(password) < 8:
            raise GraphQLError('Password must be at least 8 characters.')
        if User.objects.filter(email=email).exists():
            raise GraphQLError('A user with this email already exists.')
        return User.objects.create_user(
            email=email, password=password, role=role.value
        )

    # Deactivate a user (soft-disable login). ADMIN only. An admin cannot
    # deactivate their own account.
    @strawberry.mutation
    @require_roles(UserRole.ADMIN)
    def deactivate_user(self, info: Info, user_id: strawberry.ID) -> UserType:
        if str(info.context.request.user.id) == str(user_id):
            raise GraphQLError('You cannot deactivate your own account.')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise GraphQLError('User not found.')
        if user.is_active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        return user


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[DjangoOptimizerExtension],
)
