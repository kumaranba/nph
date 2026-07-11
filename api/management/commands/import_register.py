"""Import patients from the physical register CSV export.

Expected columns (from the handwritten register export):
    S.No, Name, Gender, D.O.A, Fees, Page#, Drug Amount, Fees Status,
    Contact, Place, Comments

Admission date format: DD-MM-YYYY
Bed is not assigned (Page# is a ledger page reference, not a bed label).
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
from api.models import Admission, AdmissionStatus, Patient

PLACEHOLDER_AGE = 0
PLACEHOLDER_DIAGNOSIS = "Unspecified"
PLACEHOLDER_DOCTOR = "Unspecified"


class Command(BaseCommand):
    help = "Import patients from the physical register CSV (no bed assignment)."

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

        with fh:
            reader = csv.DictReader(fh)
            for line_no, row in enumerate(reader, start=2):
                errors = self._import_row(row, dry_run)
                if errors:
                    row_errors.append((line_no, errors))
                else:
                    created += 1

        for line_no, errors in row_errors:
            self.stdout.write(self.style.ERROR(f"Row {line_no}: " + "; ".join(errors)))

        verb = "Would import" if dry_run else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {created} patient(s); {len(row_errors)} row(s) skipped."
            )
        )

    def _import_row(self, row, dry_run):
        def v(col):
            return (row.get(col) or "").strip()

        errors = []

        name = v("Name")
        if not name:
            errors.append("Name is required")

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

        if errors:
            return errors
        if dry_run:
            return []

        try:
            with transaction.atomic():
                patient = Patient.objects.create(
                    name=name,
                    age=PLACEHOLDER_AGE,
                    diagnosis=PLACEHOLDER_DIAGNOSIS,
                    guardian_name="",
                    guardian_phone=v("Contact"),
                    admitting_doctor=PLACEHOLDER_DOCTOR,
                )
                admission = Admission.objects.create(
                    patient=patient,
                    bed=None,
                    admission_date=admission_date,
                    monthly_fee=monthly_fee,
                    status=AdmissionStatus.ACTIVE,
                )
                BillingService.generate_invoice_for_admission(
                    admission.id, as_of=admission_date
                )
        except Exception as exc:
            return [f"unexpected error: {exc}"]

        return []
