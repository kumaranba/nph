from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    FINANCE = 'FINANCE', 'Finance'
    NURSE = 'NURSE', 'Nurse'


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using email as the login identifier.
    `password` is handled internally by AbstractBaseUser (maps to ERD's password_hash).
    """
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.NURSE)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)   # required for Django admin access
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f'{self.email} ({self.get_role_display()})'


# ---------------------------------------------------------------------------
# Room & Bed
# ---------------------------------------------------------------------------

class Room(models.Model):
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class BedStatus(models.TextChoices):
    VACANT = 'VACANT', 'Vacant'
    OCCUPIED = 'OCCUPIED', 'Occupied'


class Bed(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='beds')
    label = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=BedStatus.choices, default=BedStatus.VACANT)

    class Meta:
        unique_together = [('room', 'label')]

    def __str__(self):
        return f'{self.room.name} — {self.label}'


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

class Gender(models.TextChoices):
    MALE = 'MALE', 'Male'
    FEMALE = 'FEMALE', 'Female'
    OTHER = 'OTHER', 'Other'


class TagCategory(models.TextChoices):
    BEHAVIOUR = 'BEHAVIOUR', 'Behaviour'
    ILLNESS = 'ILLNESS', 'Illness'
    OTHER = 'OTHER', 'Other'


class Tag(models.Model):
    """A shared, reusable label applied to patients (behaviour, illness type…).

    ``name`` is the canonical, case-insensitive-unique key (lowercased); the
    original spelling is preserved in ``label`` for display. Use
    ``Tag.get_or_create_normalized`` to attach tags so spellings never
    fragment the vocabulary.
    """
    name = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=50)
    category = models.CharField(
        max_length=10, choices=TagCategory.choices, default=TagCategory.OTHER
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.label

    @classmethod
    def get_or_create_normalized(cls, raw, category=None):
        """Get or create a tag from a free-text spelling.

        Matches case-insensitively on the trimmed value; the first spelling
        seen becomes the display ``label``. Returns ``(tag, created)`` or
        ``(None, False)`` for a blank value.
        """
        label = (raw or '').strip()
        if not label:
            return None, False
        name = label.lower()
        defaults = {'label': label}
        if category:
            defaults['category'] = category
        return cls.objects.get_or_create(name=name, defaults=defaults)


class Patient(models.Model):
    """
    patient_id is auto-generated as NPH-YYYY-NNNN on first save.
    The sequential counter restarts each calendar year.
    """
    patient_id = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    diagnosis = models.TextField()
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    admitting_doctor = models.CharField(max_length=255)
    # Town/place the patient is from (from the register "Place" column).
    place = models.CharField(max_length=255, blank=True)
    tags = models.ManyToManyField('Tag', related_name='patients', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.patient_id:
            year = timezone.now().year
            prefix = f'NPH-{year}-'
            last = (
                Patient.objects
                .filter(patient_id__startswith=prefix)
                .order_by('patient_id')
                .values_list('patient_id', flat=True)
                .last()
            )
            seq = int(last.split('-')[-1]) + 1 if last else 1
            self.patient_id = f'{prefix}{seq:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.patient_id} — {self.name}'


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------

class AdmissionStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    DISCHARGED = 'DISCHARGED', 'Discharged'


class DischargeType(models.TextChoices):
    RECOVERED = 'RECOVERED', 'Recovered'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'
    AGAINST_ADVICE = 'AGAINST_ADVICE', 'Against Medical Advice'
    ABSCONDED = 'ABSCONDED', 'Absconded'
    EXPIRED = 'EXPIRED', 'Expired'


class Admission(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='admissions')
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='admissions', null=True, blank=True)
    admission_date = models.DateField()
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=12, choices=AdmissionStatus.choices, default=AdmissionStatus.ACTIVE
    )
    discharge_date = models.DateField(null=True, blank=True)
    discharge_type = models.CharField(
        max_length=15, choices=DischargeType.choices, blank=True
    )
    discharge_notes = models.TextField(blank=True)
    # Refund recorded at discharge time. Finance-only; defaults to 0.
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Unapplied advance credit; drawn down as monthly invoices come due.
    credit_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Balance carried forward from before the system (e.g. imported from the
    # paper register). Captured once as the net amount owed on
    # ``opening_balance_as_of``; represented as an is_opening_balance Invoice so
    # it flows through outstanding / payments / discharge like any other debt.
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # The date the opening balance was captured. Monthly billing resumes at the
    # first cycle date AFTER this date, so the already-covered current period is
    # not billed again (no double counting). Null for normal (non-imported)
    # admissions, which bill from admission_date as usual.
    opening_balance_as_of = models.DateField(null=True, blank=True)

    def __str__(self):
        return f'Admission #{self.pk} — {self.patient.name} ({self.status})'

    @property
    def active_fee(self):
        """The single currently-active Fee for this admission, or None."""
        return self.fees.filter(is_active=True).first()


# ---------------------------------------------------------------------------
# Fee
# ---------------------------------------------------------------------------

class Fee(models.Model):
    """A dated fee amount for an admission.

    Invariant (see CLAUDE.md): an ACTIVE admission has exactly one active Fee;
    a DISCHARGED admission has zero active Fees. Fee rows are never deleted —
    a change deactivates the current active Fee and creates a new active one,
    preserving full history.
    """
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, related_name='fees'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='created_fees',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        state = 'active' if self.is_active else 'inactive'
        return f'Fee #{self.pk} — Admission #{self.admission_id} ₹{self.amount} ({state})'


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIAL = 'PARTIAL', 'Partial'
    PAID = 'PAID', 'Paid'


class Invoice(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name='invoices')
    # The Fee this invoice was billed against, snapshotted at generation time.
    # (Nullable in migration 0006, populated in 0007, made non-null in 0008.)
    fee = models.ForeignKey(
        'Fee', on_delete=models.PROTECT, related_name='invoices',
    )
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()
    base_fee = models.DecimalField(max_digits=10, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.UNPAID
    )
    # True for the single carried-forward "opening balance" invoice seeded at
    # import. It has a sentinel period (the day before admission) so it sorts
    # oldest and never collides with a real monthly period; base_fee is 0 and
    # total_due is the imported outstanding.
    is_opening_balance = models.BooleanField(default=False)

    class Meta:
        # One invoice per billing period per admission
        unique_together = [('admission', 'billing_period_start', 'billing_period_end')]

    def __str__(self):
        return (
            f'Invoice #{self.pk} — {self.admission.patient.name} '
            f'({self.billing_period_start} → {self.billing_period_end})'
        )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentAccount(models.Model):
    """Where a payment was received (e.g. Nila, Vaigari, Bank AC).

    Managed as config data — seeded with the initial set and extendable later.
    ``is_active`` hides an account from new-payment pickers without deleting
    its history.
    """
    name = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PaymentReceipt(models.Model):
    """One payment event — the money a patient handed over in one go.

    Groups the per-invoice ``Payment`` allocations it funded, and records the
    fees-vs-charges split and the receiving account for the receipt/bill. The
    split is informational (for the receipt); allocation is still oldest-first
    across the total.
    """
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, related_name='payment_receipts'
    )
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # fees + charges
    fees_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    charges_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    account = models.ForeignKey(
        PaymentAccount, on_delete=models.PROTECT, related_name='receipts',
        null=True, blank=True,
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='payment_receipts',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_on', '-id']

    def __str__(self):
        return f'Receipt #{self.pk} — ₹{self.amount} on {self.paid_on}'


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField()
    # Null when the payment was applied automatically from advance credit
    # (no human recorder at the moment it was drawn down).
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='recorded_payments',
        null=True, blank=True,
    )
    # The receipt (payment event) this allocation belongs to. Null for
    # credit-funded auto-payments, which have no receipt.
    receipt = models.ForeignKey(
        PaymentReceipt, on_delete=models.CASCADE, related_name='payments',
        null=True, blank=True,
    )

    def __str__(self):
        return f'Payment #{self.pk} — ₹{self.amount} on {self.paid_on}'


# ---------------------------------------------------------------------------
# AdditionalCharge
# ---------------------------------------------------------------------------

class ChargeCategory(models.TextChoices):
    DRUGS = 'DRUGS', 'Drugs'
    SNACKS = 'SNACKS', 'Snacks'
    PERSONAL_CARE = 'PERSONAL_CARE', 'Personal Care'
    SPECIALIST = 'SPECIALIST', 'Specialist'
    OTHER = 'OTHER', 'Other'


class AdditionalCharge(models.Model):
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, related_name='additional_charges'
    )
    category = models.CharField(max_length=15, choices=ChargeCategory.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charge_date = models.DateField()
    description = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='recorded_charges'
    )

    def __str__(self):
        return f'{self.get_category_display()} — ₹{self.amount} on {self.charge_date}'


# ---------------------------------------------------------------------------
# VitalReading
# ---------------------------------------------------------------------------

class VitalSession(models.TextChoices):
    AM = 'AM', 'Morning (AM)'
    PM = 'PM', 'Evening (PM)'


class VitalReading(models.Model):
    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name='vital_readings'
    )
    session = models.CharField(max_length=2, choices=VitalSession.choices)
    recorded_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='recorded_vitals'
    )
    bp_systolic = models.PositiveSmallIntegerField()
    bp_diastolic = models.PositiveSmallIntegerField()
    pulse = models.PositiveSmallIntegerField()
    temperature = models.DecimalField(max_digits=4, decimal_places=1)   # e.g. 98.6
    spo2 = models.PositiveSmallIntegerField()                           # percentage 0-100
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    has_flag = models.BooleanField(default=False)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        ts = self.recorded_at.strftime('%Y-%m-%d')
        return f'Vitals — {self.admission.patient.name} {ts} ({self.session})'


# ---------------------------------------------------------------------------
# VitalsThreshold
# ---------------------------------------------------------------------------

class VitalType(models.TextChoices):
    BP_SYSTOLIC = 'BP_SYSTOLIC', 'BP Systolic'
    BP_DIASTOLIC = 'BP_DIASTOLIC', 'BP Diastolic'
    PULSE = 'PULSE', 'Pulse'
    TEMPERATURE = 'TEMPERATURE', 'Temperature'
    SPO2 = 'SPO2', 'SpO₂'
    WEIGHT = 'WEIGHT', 'Weight'


class VitalsThreshold(models.Model):
    """
    One row per vital type. Used to drive the `has_flag` logic on VitalReading.
    below_threshold: flag if reading < this value  (e.g. SpO₂ < 90)
    above_threshold: flag if reading > this value  (e.g. BP systolic > 180)
    """
    vital_type = models.CharField(
        max_length=15, choices=VitalType.choices, unique=True
    )
    below_threshold = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    above_threshold = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return (
            f'{self.get_vital_type_display()} '
            f'(below={self.below_threshold}, above={self.above_threshold})'
        )


# ---------------------------------------------------------------------------
# SystemSetting
# ---------------------------------------------------------------------------

def default_fee_due_warning_days():
    """Initial value for a fresh SystemSetting — seeded from the env-configured
    Django setting so existing deployments keep their value."""
    from django.conf import settings
    return getattr(settings, 'FEE_DUE_WARNING_DAYS', 7)


class SystemSetting(models.Model):
    """Singleton row holding editable, runtime-configurable app settings.

    Always use ``SystemSetting.load()`` — the row is pinned to pk=1.
    """
    fee_due_warning_days = models.PositiveIntegerField(
        default=default_fee_due_warning_days
    )

    class Meta:
        verbose_name = 'System settings'
        verbose_name_plural = 'System settings'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f'System settings (fee_due_warning_days={self.fee_due_warning_days})'
