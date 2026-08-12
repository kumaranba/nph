"""Import patients from the physical register CSV export.

Expected columns (from the handwritten register export):
    S.No, Name, Gender, D.O.A, Fees, Ward, Page#, Drug Amount, Fees Status,
    Contact, Place, Comments

Admission date format: DD-MM-YYYY

Gender is read from the ``Gender`` column (M/F/O or the full word) and stored
on the Patient. It is the source of truth for the patient's gender.

Ward is read from the ``Ward`` column (e.g. MW1, MW2, FW1, FW2). The ward
(Room) is auto-created on first sight, and a bed is auto-generated for the
patient within that ward (B1, B2, ...), capped at 20 beds per ward. A blank
or over-capacity ward imports the patient without a bed and emits a warning.
By convention a ``MW`` prefix is a male ward and ``FW`` a female ward; a
patient whose gender disagrees with the ward prefix is imported anyway with a
warning.

Missing fields (age, diagnosis, admitting_doctor) are set to placeholder
values that staff can update via the application later.

Usage:
    python manage.py import_register patient_register.csv
    python manage.py import_register patient_register.csv --dry-run
"""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Gender,
    Patient,
    Room,
)

PLACEHOLDER_AGE = 0
PLACEHOLDER_DIAGNOSIS = "Unspecified"
PLACEHOLDER_DOCTOR = "Unspecified"

# Max auto-generated beds per ward.
WARD_BED_CAP = 20

# Free-text gender values → canonical Gender choice.
GENDER_ALIASES = {
    "M": Gender.MALE,
    "MALE": Gender.MALE,
    "F": Gender.FEMALE,
    "FEMALE": Gender.FEMALE,
    "O": Gender.OTHER,
    "OTHER": Gender.OTHER,
}

# Ward-name prefix → gender it is conventionally reserved for.
WARD_PREFIX_GENDER = {
    "MW": Gender.MALE,
    "FW": Gender.FEMALE,
}


class Command(BaseCommand):
    help = "Import patients from the physical register CSV, assigning beds by ward."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the register CSV file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report without creating any records.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        dry_run = options["dry_run"]

        try:
            fh = open(path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Cannot open {path}: {exc}")

        created = 0
        row_errors = []
        row_warnings = []

        with fh:
            reader = csv.DictReader(fh)
            for line_no, row in enumerate(reader, start=2):
                errors, warnings = self._import_row(row, dry_run)
                if warnings:
                    row_warnings.append((line_no, warnings))
                if errors:
                    row_errors.append((line_no, errors))
                else:
                    created += 1

        for line_no, warnings in row_warnings:
            self.stdout.write(
                self.style.WARNING(f"Row {line_no}: " + "; ".join(warnings))
            )
        for line_no, errors in row_errors:
            self.stdout.write(self.style.ERROR(f"Row {line_no}: " + "; ".join(errors)))

        verb = "Would import" if dry_run else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {created} patient(s); {len(row_errors)} row(s) skipped; "
                f"{len(row_warnings)} row(s) with warnings."
            )
        )

    def _import_row(self, row, dry_run):
        def v(col):
            return (row.get(col) or "").strip()

        errors = []
        warnings = []

        name = v("Name")
        if not name:
            errors.append("Name is required")

        # Gender (optional; stored as the source of truth for the patient).
        gender = ""
        raw_gender = v("Gender")
        if raw_gender:
            gender_choice = GENDER_ALIASES.get(raw_gender.upper())
            if gender_choice is None:
                warnings.append(f"unrecognized Gender '{raw_gender}', left blank")
            else:
                gender = gender_choice.value

        admission_date = None
        raw_date = v("D.O.A")
        if not raw_date:
            errors.append("D.O.A is required")
        else:
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    admission_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            if admission_date is None:
                errors.append(f"D.O.A '{raw_date}' must be DD-MM-YYYY")

        monthly_fee = None
        raw_fee = v("Fees")
        if not raw_fee:
            errors.append("Fees is required")
        else:
            try:
                monthly_fee = Decimal(raw_fee.replace(",", ""))
                if monthly_fee < 0:
                    errors.append("Fees must be non-negative")
            except InvalidOperation:
                errors.append(f"Fees '{raw_fee}' is not a valid number")

        # Ward (optional). Gender-vs-ward mismatch is a warning, not an error.
        ward = v("Ward").upper()
        if ward and gender:
            expected = WARD_PREFIX_GENDER.get(ward[:2])
            if expected is not None and expected.value != gender:
                warnings.append(
                    f"ward '{ward}' is a {expected.label.lower()} ward but "
                    f"patient gender is {gender}"
                )

        if errors:
            return errors, warnings
        if dry_run:
            return [], warnings

        try:
            with transaction.atomic():
                patient = Patient.objects.create(
                    name=name,
                    age=PLACEHOLDER_AGE,
                    gender=gender,
                    diagnosis=PLACEHOLDER_DIAGNOSIS,
                    guardian_name="",
                    guardian_phone=v("Contact"),
                    admitting_doctor=PLACEHOLDER_DOCTOR,
                )
                bed = None
                if ward:
                    bed, bed_warning = self._assign_bed(ward)
                    if bed_warning:
                        warnings.append(bed_warning)
                admission = Admission.objects.create(
                    patient=patient,
                    bed=bed,
                    admission_date=admission_date,
                    monthly_fee=monthly_fee,
                    status=AdmissionStatus.ACTIVE,
                )
                if bed is not None:
                    bed.status = BedStatus.OCCUPIED
                    bed.save(update_fields=["status"])
                BillingService.generate_invoice_for_admission(
                    admission.id, as_of=admission_date
                )
        except Exception as exc:
            return [f"unexpected error: {exc}"], warnings

        return [], warnings

    def _assign_bed(self, ward):
        """Get-or-create the ward Room and auto-generate the next bed in it.

        Returns ``(bed, warning)``. ``bed`` is None (with a warning) when the
        ward is already at the per-ward bed cap.
        """
        room, _ = Room.objects.get_or_create(
            name=ward, defaults={"capacity": WARD_BED_CAP}
        )
        bed_count = room.beds.count()
        if bed_count >= WARD_BED_CAP:
            return None, f"ward '{ward}' is full ({WARD_BED_CAP} beds); imported without a bed"
        bed = Bed.objects.create(
            room=room,
            label=f"B{bed_count + 1}",
            status=BedStatus.VACANT,
        )
        return bed, None
