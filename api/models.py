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

class Patient(models.Model):
    """
    patient_id is auto-generated as NPH-YYYY-NNNN on first save.
    The sequential counter restarts each calendar year.
    """
    patient_id = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=255)
    age = models.PositiveIntegerField()
    diagnosis = models.TextField()
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    admitting_doctor = models.CharField(max_length=255)
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
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='admissions')
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

    def __str__(self):
        return f'Admission #{self.pk} — {self.patient.name} ({self.status})'


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIAL = 'PARTIAL', 'Partial'
    PAID = 'PAID', 'Paid'


class Invoice(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name='invoices')
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()
    base_fee = models.DecimalField(max_digits=10, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.UNPAID
    )

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

class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField()
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='recorded_payments'
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
