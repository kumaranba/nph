"""Import a past-discharge list, for PRO follow-up.

Each row creates a Patient (if new) and a DISCHARGED Admission for a historical
stay, so the person shows up in the Discharged list and can be followed up. This
is a follow-up record only — no fees, invoices, opening balances, or beds are
created (``monthly_fee`` is stored from the FEES column for reference only).

Expected columns (header row required; matched case-insensitively):
    Patient Name, D.O.A, D.O.D, FEES, CONTACT, PLACE

    D.O.A / D.O.D: day-first, e.g. 30/08/25, 30/08/2025, 30-08-2025, 2026-08-30.
    FEES: a number (commas / ₹ tolerated); blank or NIL → 0.

Re-admissions are handled safely:
  * A patient is matched to an existing record **phone-first** (by CONTACT),
    falling back to name when there's no phone. A new Patient is created only
    when there's no match. Ambiguous matches (several patients share the phone
    or name) are reported and the row is skipped for you to resolve by hand.
  * If a matched patient currently has an ACTIVE admission (they were
    re-admitted and are still in-house), the historical discharged stay is added
    **alongside** it — the active admission and its bed are never touched.
  * The same person can appear several times (discharged, re-admitted,
    discharged again). Each becomes its own discharged admission, deduped by
    (patient + admission date + discharge date), so re-running never doubles up.

The 'Discharged' tag is NOT set here — run ``backfill_discharged_tags``
afterwards; it tags discharged patients and correctly skips anyone still active.

Usage:
    python manage.py import_discharged discharges.csv --dry-run
    python manage.py import_discharged discharges.csv
"""
import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Admission, AdmissionStatus, Patient
from api.phones import normalize_phone

PLACEHOLDER_DIAGNOSIS = "Unspecified"
PLACEHOLDER_DOCTOR = "Unspecified"

# Accepted date formats, day-first (2-digit year maps per Python's %y).
DATE_FORMATS = (
    "%d/%m/%y", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y",
    "%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d",
)

# Header aliases → canonical field (compared lowercased/stripped).
_ALIASES = {
    "patient name": "name", "name": "name",
    "d.o.a": "doa", "doa": "doa", "admission date": "doa",
    "d.o.d": "dod", "dod": "dod", "discharge date": "dod",
    "fees": "fees", "fee": "fees",
    "contact": "contact", "phone": "contact", "mobile": "contact",
    "place": "place",
}


def _parse_date(raw):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_fees(raw):
    """(value, ok). Blank / NIL → (0, True). Unparseable → (0, False)."""
    s = (raw or "").strip()
    if not s or s.upper() in {"NIL", "NA", "N/A", "-"}:
        return Decimal("0"), True
    cleaned = re.sub(r"[₹,\s]", "", s)
    try:
        return Decimal(cleaned), True
    except InvalidOperation:
        return Decimal("0"), False


class Command(BaseCommand):
    help = "Import a past-discharge list (Patient Name, D.O.A, D.O.D, FEES, CONTACT, PLACE)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the discharge-list CSV.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Validate and report without writing anything.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        dry_run = options["dry_run"]

        try:
            fh = open(path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Cannot open {path}: {exc}")

        # Within-run state (so re-admissions in the same file group correctly,
        # in both dry-run and real mode).
        self._run_patients = {}      # canonical key → Patient (or None in dry-run)
        self._seen_adm = set()       # (canonical key, doa, dod)

        self.patients_created = 0
        self.patients_matched = 0
        self.admissions_created = 0
        self.skipped_dupe = 0
        row_errors = []
        row_warnings = []

        with fh:
            reader = csv.DictReader(fh)
            headers = {(_ALIASES.get((h or "").strip().lower())) for h in (reader.fieldnames or [])}
            for required in ("name", "doa", "dod"):
                if required not in headers:
                    raise CommandError(
                        "Missing required column(s). Need at least Patient Name, "
                        "D.O.A, D.O.D (also reads FEES, CONTACT, PLACE)."
                    )

            ctx = transaction.atomic() if not dry_run else _NullCtx()
            with ctx:
                for line_no, row in enumerate(reader, start=2):
                    errors, warnings = self._import_row(row, dry_run)
                    if warnings:
                        row_warnings.append((line_no, warnings))
                    if errors:
                        row_errors.append((line_no, errors))

        for line_no, warnings in row_warnings:
            self.stdout.write(self.style.WARNING(f"Row {line_no}: " + "; ".join(warnings)))
        for line_no, errors in row_errors:
            self.stdout.write(self.style.ERROR(f"Row {line_no}: " + "; ".join(errors)))

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{verb}: {self.patients_created} new patient(s), "
            f"{self.admissions_created} discharged admission(s). "
            f"Matched {self.patients_matched} existing patient(s); "
            f"{self.skipped_dupe} duplicate admission(s) skipped; "
            f"{len(row_errors)} row(s) skipped on error; "
            f"{len(row_warnings)} warning(s)."
        ))
        if not dry_run and self.admissions_created:
            self.stdout.write(
                "Next: run `python manage.py backfill_discharged_tags` to tag them."
            )

    # ---- row ----
    def _import_row(self, row, dry_run):
        def v(col):
            # Resolve by canonical alias so header spelling/case doesn't matter.
            for k, val in row.items():
                if _ALIASES.get((k or "").strip().lower()) == col:
                    return (val or "").strip()
            return ""

        errors, warnings = [], []

        name = v("name")
        if not name:
            errors.append("Patient Name is required")

        doa = _parse_date(v("doa")) if v("doa") else None
        if v("doa") and doa is None:
            errors.append(f"unparseable D.O.A '{v('doa')}'")
        elif not v("doa"):
            errors.append("D.O.A is required")

        dod = _parse_date(v("dod")) if v("dod") else None
        if v("dod") and dod is None:
            errors.append(f"unparseable D.O.D '{v('dod')}'")
        elif not v("dod"):
            errors.append("D.O.D is required")

        if doa and dod and dod < doa:
            errors.append("D.O.D is before D.O.A")

        fees, fees_ok = _parse_fees(v("fees"))
        if not fees_ok:
            warnings.append(f"unparseable FEES '{v('fees')}', stored 0")

        if errors:
            return errors, warnings

        contact = v("contact")
        place = v("place")
        ckey = _canonical_key(contact, name)

        # --- match / create patient ---
        if ckey in self._run_patients:
            patient = self._run_patients[ckey]
            self.patients_matched += 1
        else:
            patient, ambiguous, matched_by = self._match_patient(contact, name)
            if ambiguous:
                errors.append(
                    f"ambiguous match for '{name}'"
                    + (f" / {contact}" if contact else "")
                    + " — several patients match; resolve manually"
                )
                return errors, warnings
            if patient is None:
                if not dry_run:
                    patient = Patient.objects.create(
                        name=name,
                        guardian_phone=contact[:20],
                        place=place,
                        diagnosis=PLACEHOLDER_DIAGNOSIS,
                        admitting_doctor=PLACEHOLDER_DOCTOR,
                    )
                self.patients_created += 1
            else:
                self.patients_matched += 1
                if matched_by == "name" and contact:
                    warnings.append("matched by name (phone not found on record)")
            self._run_patients[ckey] = patient

        # --- dedupe + create the discharged admission ---
        adm_key = (ckey, doa, dod)
        already = adm_key in self._seen_adm or (
            patient is not None
            and Admission.objects.filter(
                patient=patient, admission_date=doa,
                discharge_date=dod, status=AdmissionStatus.DISCHARGED,
            ).exists()
        )
        self._seen_adm.add(adm_key)
        if already:
            self.skipped_dupe += 1
            return errors, warnings

        if not dry_run:
            Admission.objects.create(
                patient=patient,
                bed=None,
                monthly_fee=fees,
                admission_date=doa,
                discharge_date=dod,
                status=AdmissionStatus.DISCHARGED,
            )
        self.admissions_created += 1
        return errors, warnings

    # ---- matching ----
    def _match_patient(self, contact, name):
        """Return (patient_or_None, ambiguous, matched_by). Phone first, then
        name."""
        norm = normalize_phone(contact) if contact else ""
        if norm:
            # Normalize both sides — stored phones vary in formatting (+91,
            # spaces, trunk 0), so compare the canonical E.164 form, not text.
            candidates = Patient.objects.exclude(guardian_phone="").only(
                "id", "guardian_phone"
            )
            matches = [p for p in candidates if normalize_phone(p.guardian_phone) == norm]
            if len(matches) == 1:
                return matches[0], False, "phone"
            if len(matches) > 1:
                return None, True, "phone"

        key = name.strip().lower()
        by_name = [p for p in Patient.objects.filter(name__iexact=key)]
        if len(by_name) == 1:
            return by_name[0], False, "name"
        if len(by_name) > 1:
            return None, True, "name"
        return None, False, ""


def _canonical_key(contact, name):
    norm = normalize_phone(contact) if contact else ""
    return f"phone:{norm}" if norm else f"name:{name.strip().lower()}"


class _NullCtx:
    """No-op context manager for dry-run (no transaction)."""
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
