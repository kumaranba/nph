"""Bulk-import patients from a CSV template.

Each row creates a Patient, an active Admission into a named bed, and the
first Invoice for that admission's billing period. Rows are validated and
imported independently — a bad row is reported and skipped, the rest proceed.

CSV columns (header required):
    name, diagnosis, admitting_doctor, room, bed, admission_date,
    monthly_fee, guardian_name (optional), guardian_phone (optional)

    admission_date: YYYY-MM-DD

Usage:
    python manage.py import_patients patients.csv
    python manage.py import_patients patients.csv --dry-run
"""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.billing import BillingService
from api.models import Admission, AdmissionStatus, Bed, BedStatus, Patient

REQUIRED_COLUMNS = [
    "name",
    "diagnosis",
    "admitting_doctor",
    "room",
    "bed",
    "admission_date",
    "monthly_fee",
]
OPTIONAL_COLUMNS = ["guardian_name", "guardian_phone"]


class Command(BaseCommand):
    help = (
        "Import patients (+ admission + first invoice) from a CSV. Columns: "
        + ", ".join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the CSV file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate rows and report errors without creating anything.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        dry_run = options["dry_run"]

        try:
            handle = open(path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Cannot open {path}: {exc}")

        created = 0
        row_errors = []

        with handle:
            reader = csv.DictReader(handle)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise CommandError("CSV is missing columns: " + ", ".join(missing))

            # Row 1 is the header, so data rows start at line 2.
            for line_no, row in enumerate(reader, start=2):
                errors = self._import_row(row, dry_run)
                if errors:
                    row_errors.append((line_no, errors))
                else:
                    created += 1

        for line_no, errors in row_errors:
            self.stdout.write(
                self.style.ERROR(f"Row {line_no}: " + "; ".join(errors))
            )

        verb = "Would import" if dry_run else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {created} patient(s); {len(row_errors)} row(s) skipped."
            )
        )

    def _import_row(self, row, dry_run):
        """Validate one row; if valid and not a dry run, create the records.
        Returns a list of error strings (empty means success)."""
        errors = []

        def value(col):
            return (row.get(col) or "").strip()

        for col in REQUIRED_COLUMNS:
            if not value(col):
                errors.append(f"{col} is required")

        monthly_fee = None
        if value("monthly_fee"):
            try:
                monthly_fee = Decimal(value("monthly_fee"))
                if monthly_fee < 0:
                    errors.append("monthly_fee must be non-negative")
            except InvalidOperation:
                errors.append("monthly_fee must be a number")

        admission_date = None
        if value("admission_date"):
            try:
                admission_date = datetime.strptime(
                    value("admission_date"), "%Y-%m-%d"
                ).date()
            except ValueError:
                errors.append("admission_date must be YYYY-MM-DD")

        bed = None
        if value("room") and value("bed"):
            bed = (
                Bed.objects.select_related("room")
                .filter(room__name=value("room"), label=value("bed"))
                .first()
            )
            if bed is None:
                errors.append(f"bed '{value('bed')}' in room '{value('room')}' not found")
            elif bed.status == BedStatus.OCCUPIED:
                errors.append(f"bed '{value('bed')}' is already occupied")

        if errors:
            return errors
        if dry_run:
            return []

        try:
            with transaction.atomic():
                # Re-fetch under a lock and re-check to avoid a race where an
                # earlier row in this same import took the bed.
                bed = Bed.objects.select_for_update().get(pk=bed.pk)
                if bed.status == BedStatus.OCCUPIED:
                    return [f"bed '{value('bed')}' is already occupied"]

                patient = Patient.objects.create(
                    name=value("name"),
                    diagnosis=value("diagnosis"),
                    guardian_name=value("guardian_name"),
                    guardian_phone=value("guardian_phone"),
                    admitting_doctor=value("admitting_doctor"),
                )
                admission = Admission.objects.create(
                    patient=patient,
                    bed=bed,
                    admission_date=admission_date,
                    monthly_fee=monthly_fee,
                    status=AdmissionStatus.ACTIVE,
                )
                bed.status = BedStatus.OCCUPIED
                bed.save(update_fields=["status"])

                BillingService.generate_invoice_for_admission(
                    admission.id, as_of=admission_date
                )
        except Exception as exc:  # pragma: no cover - defensive
            return [f"unexpected error: {exc}"]

        return []
