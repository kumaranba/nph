"""Backfill the +30-day aftercare follow-up for already-discharged patients.

New discharges schedule this automatically; this covers admissions discharged
before that behaviour existed. Idempotent — one aftercare follow-up per
admission. Skips admissions with no discharge date.

Usage:
    python manage.py reconcile_aftercare
    python manage.py reconcile_aftercare --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand

from api.models import Admission, AdmissionStatus, FollowUp, FollowUpKind

AFTERCARE_DAYS = 30


class Command(BaseCommand):
    help = "Create the +30-day aftercare follow-up for past discharges."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created = 0
        qs = (
            Admission.objects
            .filter(status=AdmissionStatus.DISCHARGED, discharge_date__isnull=False)
            .select_related("patient")
        )
        for adm in qs:
            if FollowUp.objects.filter(
                admission=adm, kind=FollowUpKind.AFTERCARE
            ).exists():
                continue
            if not dry_run:
                FollowUp.objects.create(
                    patient=adm.patient, admission=adm,
                    kind=FollowUpKind.AFTERCARE, note="Aftercare review",
                    follow_up_date=adm.discharge_date + timedelta(days=AFTERCARE_DAYS),
                )
            created += 1

        verb = "Would schedule" if dry_run else "Scheduled"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created} aftercare follow-up(s)."
        ))
